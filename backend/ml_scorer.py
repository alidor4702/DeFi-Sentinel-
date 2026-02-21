"""
XGBoost v3 model scorer
Maps live-collected features → 54 model features → rug probability.

When deployer history is unavailable (the most important feature group,
accounting for ~89 % of model importance), we use dataset-median "neutral"
defaults and **blend** the ML prediction with an enhanced heuristic that
relies on observable on-chain signals (liquidity, pool age, metadata …).
"""

import json
import logging
import math
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger("ml_scorer")

# ── ML dependencies (optional — graceful fallback if missing) ─────────────
try:
    import numpy as np
    import xgboost as xgb

    _ML_AVAILABLE = True
except ImportError:
    _ML_AVAILABLE = False
    logger.warning("xgboost/numpy not installed — ML scoring disabled, using heuristic")

# ── Model artefacts ───────────────────────────────────────────────────────
_MODEL_DIR = Path(__file__).resolve().parent.parent / "models"
_model = None
_feature_names: list[str] = []
_model_meta: dict | None = None

# ── Dataset-median "neutral" deployer defaults ────────────────────────────
# When the live collector cannot determine deployer history (e.g. the
# getAssetsByAuthority/Creator RPC returns nothing), we substitute these
# median values from the enriched training set so the 89 %-weighted deployer
# block doesn't collapse to "all-zero == unknown == rug".
_NEUTRAL_DEPLOYER = {
    "feat_deployer_past_tokens":    1240,     # median of training set
    "feat_deployer_past_rugs":      0,
    "feat_deployer_past_rug_rate":  0.0,
    "feat_deployer_past_labeled":   262,      # median of training set
    "feat_deployer_past_is_serial": 0,
}

# Blend weights when deployer data is missing
_ML_WEIGHT_NO_DEPLOYER  = 0.35   # ML with neutral defaults
_HEU_WEIGHT_NO_DEPLOYER = 0.65   # Heuristic (on-chain signals)

# ── Established-token thresholds ──────────────────────────────────────────
# A token that has survived with this much liquidity for this long is by
# definition NOT a rug-pull.  We cap the risk score accordingly.
_ESTABLISHED_TIERS = [
    # (min_liq_usd, min_age_hours, max_risk)
    (1_000_000,  720, 25),   # $1M+ liq,  30 d+ → max risk 25
    (  100_000,  168, 40),   # $100k+ liq, 7 d+ → max risk 40
    (   10_000,   72, 55),   # $10k+ liq,  3 d+ → max risk 55
]

# ── Constants for feature engineering ─────────────────────────────────────
SCAM_WORDS = frozenset({
    "elon", "musk", "doge", "shib", "safe", "moon", "rocket", "gem",
    "100x", "1000x", "inu", "baby", "mini", "floki", "pepe", "wojak",
    "chad", "based", "trump", "biden", "grok", "ai", "gpt",
})

COMMON_SUPPLIES = frozenset({
    1_000_000, 10_000_000, 100_000_000, 1_000_000_000,
    10_000_000_000, 100_000_000_000, 1_000_000_000_000,
    420_690_000_000, 69_420_000_000, 999_999_999,
})

_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002702-\U000027B0"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "\U00002600-\U000026FF"
    "]"
)


# ── Model loading ─────────────────────────────────────────────────────────
def _load_model():
    global _model, _feature_names, _model_meta
    if _model is not None or not _ML_AVAILABLE:
        return
    try:
        _model = xgb.XGBClassifier()
        _model.load_model(str(_MODEL_DIR / "model_v3.json"))
        with open(_MODEL_DIR / "feature_list_v3.json") as fh:
            _feature_names = json.load(fh)
        with open(_MODEL_DIR / "model_meta_v3.json") as fh:
            _model_meta = json.load(fh)
        logger.info(
            "ML model v3 loaded: %d features, AUC=%.4f",
            len(_feature_names),
            _model_meta["metrics"]["auc_roc"],
        )
    except Exception as exc:
        logger.error("Failed to load ML model: %s", exc)
        _model = None


def get_model_meta() -> dict | None:
    """Return model metadata (version, metrics, top features)."""
    _load_model()
    return _model_meta


# ── Helpers ────────────────────────────────────────────────────────────────
def _tz(n) -> int:
    """Count trailing zeros of an integer."""
    if n is None or n == 0:
        return 0
    s = str(int(abs(n)))
    return len(s) - len(s.rstrip("0"))


def _liq_bucket(liq: float) -> int:
    if liq <= 0:
        return 0
    if liq < 100:
        return 1
    if liq < 1_000:
        return 2
    if liq < 10_000:
        return 3
    if liq < 100_000:
        return 4
    if liq < 1_000_000:
        return 5
    return 6


# ── Deployer-data availability check ──────────────────────────────────────
def _deployer_data_available(features: dict) -> bool:
    """Return True if the collector actually found deployer history."""
    return (
        (features.get("deployer_past_tokens") or 0) > 0
        or (features.get("deployer_past_labeled") or 0) > 0
        or (features.get("deployer_past_rugs") or 0) > 0
    )


# ── Feature mapping (live → 54 model features) ───────────────────────────
def _map(f: dict, *, neutral_deployer: bool = False) -> dict:
    """Map live collector features → 54 model training features.

    When *neutral_deployer* is True the 5 deployer features are filled with
    dataset-median values instead of the (all-zero) collector output.  This
    prevents the 89 %-weighted deployer block from dominating the prediction
    when we simply couldn't look up the deployer's history.
    """
    name = f.get("token_name") or ""
    symbol = f.get("token_symbol") or ""
    supply = f.get("token_supply") or 0
    decimals = f.get("token_decimals") or 0
    liq = f.get("gt_reserve_usd") or f.get("rc_total_market_liquidity") or 0
    now = datetime.now(timezone.utc)

    m: dict[str, float] = {}

    # ── Base (12) ──
    m["TOTAL_ADDED_LIQUIDITY"] = liq
    m["NUM_LIQUIDITY_ADDS"] = 1
    m["HAS_METADATA"] = int(bool(f.get("metadata_uri") or f.get("metadata_uri_reachable")))
    m["HAS_IMAGE"] = int(bool(f.get("has_image")))
    m["HAS_JSON_URI"] = int(bool(f.get("metadata_uri")))
    m["TOKEN_DECIMALS"] = decimals
    m["TOKEN_SUPPLY"] = supply
    m["IS_MUTABLE"] = int(bool(f.get("is_mutable")))
    m["ROYALTY_PCT"] = 0
    m["NUM_CREATORS"] = 1
    m["CREATOR_VERIFIED"] = 0
    m["MINT_AUTHORITY_ACTIVE"] = int(f.get("mint_authority_revoked") is False)

    # ── Derived (6) ──
    m["derived_avg_add_size"] = liq
    metas = [f.get(k) for k in ("has_image", "has_description", "has_website", "has_twitter", "has_telegram")]
    known = [v for v in metas if v is not None]
    m["derived_metadata_completeness"] = sum(bool(v) for v in known) / len(known) if known else 0.5
    m["derived_log_supply"] = math.log(supply + 1) if supply > 0 else 0
    m["derived_supply_decimal_ratio"] = supply / (10 ** decimals) if decimals > 0 else supply
    m["derived_uri_domain_rug_rate"] = 0.5
    m["derived_token_std_rug_rate"] = 0.5

    # ── Name (9) ──
    m["feat_name_length"] = len(name)
    m["feat_name_is_empty"] = int(not name)
    m["feat_name_all_caps"] = int(name.isupper() and len(name) > 0)
    m["feat_name_has_numbers"] = int(any(c.isdigit() for c in name))
    m["feat_name_has_emoji"] = int(bool(_EMOJI_RE.search(name)))
    m["feat_name_has_scam_word"] = int(any(w in name.lower() for w in SCAM_WORDS))
    m["feat_name_word_count"] = len(name.split()) if name else 0
    m["feat_name_starts_with_dollar"] = int(name.startswith("$"))
    m["feat_name_frequency"] = 0.0

    # ── Symbol (5) ──
    m["feat_symbol_length"] = len(symbol)
    m["feat_symbol_is_empty"] = int(not symbol)
    m["feat_symbol_all_caps"] = int(symbol.isupper() and len(symbol) > 0)
    m["feat_symbol_has_numbers"] = int(any(c.isdigit() for c in symbol))
    m["feat_symbol_frequency"] = 0.0

    # ── Pool time (6) ──
    age_h = f.get("gt_pool_age_hours")
    pt = now - timedelta(hours=age_h) if age_h else now
    m["feat_pool_hour"] = pt.hour
    m["feat_pool_day_of_week"] = pt.weekday()
    m["feat_pool_is_weekend"] = int(pt.weekday() >= 5)
    m["feat_pool_month"] = pt.month
    m["feat_pool_is_night"] = int(pt.hour <= 6 or pt.hour >= 22)
    m["feat_pool_days_since_2022"] = (pt - datetime(2022, 1, 1, tzinfo=timezone.utc)).days

    # ── Supply (6) ──
    m["feat_supply_log"] = math.log10(supply + 1) if supply > 0 else 0
    m["feat_supply_is_zero"] = int(supply == 0)
    m["feat_supply_trailing_zeros"] = _tz(supply)
    m["feat_supply_is_round_million"] = int(supply > 0 and supply % 1_000_000 == 0)
    m["feat_supply_is_round_billion"] = int(supply > 0 and supply % 1_000_000_000 == 0)
    m["feat_supply_is_exact_common"] = int(int(supply) in COMMON_SUPPLIES)

    # ── Liquidity (5) ──
    m["feat_liq_log"] = math.log10(liq + 1) if liq > 0 else 0
    m["feat_liq_is_zero"] = int(liq == 0)
    m["feat_liq_bucket"] = _liq_bucket(liq)
    m["feat_liq_trailing_zeros"] = _tz(liq)
    m["feat_supply_to_liq_ratio"] = supply / (liq + 1)

    # ── Deployer (5) ──
    if neutral_deployer:
        for k, v in _NEUTRAL_DEPLOYER.items():
            m[k] = v
    else:
        m["feat_deployer_past_tokens"] = f.get("deployer_past_tokens", 0)
        m["feat_deployer_past_rugs"] = f.get("deployer_past_rugs", 0)
        m["feat_deployer_past_rug_rate"] = f.get("deployer_past_rug_rate", 0.0)
        m["feat_deployer_past_labeled"] = f.get("deployer_past_labeled", 0)
        m["feat_deployer_past_is_serial"] = int(f.get("deployer_past_is_serial", False))

    return m


# ── Prediction ─────────────────────────────────────────────────────────────
def _established_cap(features: dict, score: int) -> int:
    """Cap the risk score for tokens that are clearly established.

    A token with >$1 M liquidity that has been live for 30+ days is by
    definition not a rug-pull (the whole point of a rug is to drain
    liquidity quickly).  We cap the score so such tokens never show as
    DANGER, even if the ML model is confused by deployer history.
    """
    liq = features.get("gt_reserve_usd") or features.get("rc_total_market_liquidity") or 0
    age = features.get("gt_pool_age_hours") or 0
    for min_liq, min_age, cap in _ESTABLISHED_TIERS:
        if liq >= min_liq and age >= min_age:
            if score > cap:
                logger.debug(
                    "Established-token cap: liq=%.0f age=%.1fh → cap %d → %d",
                    liq, age, score, cap,
                )
            return min(score, cap)
    return score


def predict_rug_probability(features: dict) -> tuple[float, int]:
    """
    Return (rug_probability 0‑1, risk_score 0‑100).

    When the deployer history is available the full ML model is used as-is.
    When it is **not** available (which is the common case for live scans
    because getAssetsByAuthority rarely returns past tokens), we:
      1. Run the ML model with neutral dataset-median deployer defaults.
      2. Run an enhanced heuristic based on observable on-chain signals.
      3. Blend them so the heuristic drives most of the decision.

    In **all** cases an established-token cap is applied: tokens with very
    high liquidity and age cannot exceed a ceiling risk score.
    """
    _load_model()
    if _model is None or not _feature_names:
        prob, score = _heuristic_fallback(features)
        score = _established_cap(features, score)
        return score / 100, score

    has_deployer = _deployer_data_available(features)

    if has_deployer:
        # ── Full ML with real deployer data ──
        mapped = _map(features, neutral_deployer=False)
        vec = [float(mapped.get(n, 0) or 0) for n in _feature_names]
        try:
            X = np.array([vec], dtype=np.float32)
            proba = _model.predict_proba(X)[0]
            rug_p = float(proba[1])
            raw_score = max(0, min(100, round(rug_p * 100)))
            score = _established_cap(features, raw_score)
            return score / 100, score
        except Exception as exc:
            logger.error("ML prediction failed: %s", exc)
            prob, score = _heuristic_fallback(features)
            score = _established_cap(features, score)
            return score / 100, score

    # ── Deployer data unavailable — blended approach ──
    logger.debug("Deployer data unavailable — using neutral defaults + heuristic blend")

    # ML with neutral deployer defaults
    mapped = _map(features, neutral_deployer=True)
    vec = [float(mapped.get(n, 0) or 0) for n in _feature_names]
    try:
        X = np.array([vec], dtype=np.float32)
        proba = _model.predict_proba(X)[0]
        ml_rug_p = float(proba[1])
    except Exception:
        ml_rug_p = 0.5   # fallback to neutral

    h_prob, _ = _heuristic_fallback(features)

    blended = _ML_WEIGHT_NO_DEPLOYER * ml_rug_p + _HEU_WEIGHT_NO_DEPLOYER * h_prob
    raw_score = max(0, min(100, round(blended * 100)))
    score = _established_cap(features, raw_score)
    logger.debug(
        "Blended score: ML(neutral)=%.3f  heuristic=%.3f  final=%.3f (%d)",
        ml_rug_p, h_prob, blended, score,
    )
    return score / 100, score


def _heuristic_fallback(f: dict) -> tuple[float, int]:
    """
    Enhanced heuristic scoring based on observable on-chain signals.

    Starts at a neutral 45 and adjusts up (risky) or down (legit) based on
    liquidity, pool age, authority status, holder concentration, metadata
    quality, and RugCheck score.  Designed to handle both established tokens
    (USDC, BONK) and fresh pump.fun launches accurately.
    """
    s = 45.0  # slightly below neutral

    # ── RugCheck score (0 = good, higher = bad) ──
    rc = f.get("rc_score")
    if rc is not None:
        if rc == 0:
            s -= 12
        elif rc < 300:
            s -= 5
        elif rc > 700:
            s += 15
        elif rc > 500:
            s += 8

    # ── Liquidity — strongest on-chain legit signal ──
    liq = f.get("gt_reserve_usd") or f.get("rc_total_market_liquidity") or 0
    if liq > 1_000_000:
        s -= 30          # >$1M liquidity – very established
    elif liq > 100_000:
        s -= 20
    elif liq > 10_000:
        s -= 8
    elif liq < 500:
        s += 12
    elif liq < 2_000:
        s += 8

    # ── Pool age — another strong legit signal ──
    age = f.get("gt_pool_age_hours") or 0
    if age > 720:         # >30 days
        s -= 20
    elif age > 168:       # >1 week
        s -= 12
    elif age > 24:
        s -= 4
    elif age < 1:
        s += 15
    elif age < 6:
        s += 10
    elif age < 24:
        s += 5

    # ── Mint authority (contextual) ──
    # Active mint authority is risky on new/low-liq tokens but normal for
    # established tokens (e.g. USDC keeps mint authority for compliance).
    is_established = liq > 100_000 or age > 720
    if f.get("mint_authority_revoked") is False and not is_established:
        s += 12
    elif f.get("mint_authority_revoked") is True:
        s -= 3    # good sign – authority burned

    # ── Freeze authority ──
    if f.get("freeze_authority_revoked") is False and not is_established:
        s += 8

    # ── Top-holder concentration ──
    top = f.get("rc_top_holder_pct")
    if top is not None:
        if top > 80:
            s += 15
        elif top > 50:
            s += min((top - 50) * 0.4, 12)
        elif top < 15:
            s -= 5

    # ── Metadata quality ──
    if f.get("is_mutable"):
        s += 3
    if not f.get("has_image"):
        s += 5
    metas = ["has_description", "has_website", "has_twitter", "has_telegram"]
    filled = sum(1 for k in metas if f.get(k))
    s -= filled * 2  # up to -8 for good socials

    # ── Name signals ──
    name = (f.get("token_name") or "").lower()
    if any(w in name for w in SCAM_WORDS):
        s += 6

    # ── 24 h volume (if available from GeckoTerminal) ──
    vol = f.get("gt_volume_24h")
    if vol is not None:
        if vol > 100_000:
            s -= 8
        elif vol > 10_000:
            s -= 4
        elif vol < 100:
            s += 5

    # ── Jupiter verified ──
    if f.get("jup_verified"):
        s -= 10
    if f.get("jup_daily_volume") and f["jup_daily_volume"] > 50_000:
        s -= 5

    score = max(0, min(100, round(s)))
    return score / 100, score
