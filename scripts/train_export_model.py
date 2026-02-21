"""
DeFi Sentinel — Train & Export Production Model
Trains the XGBoost model and exports it for the FastAPI backend.
Outputs:
  - models/model.json        (XGBoost model)
  - models/feature_list.json (ordered feature names)
  - models/model_meta.json   (metrics, thresholds, info)
"""
import pandas as pd
import numpy as np
from sklearn.metrics import (roc_auc_score, precision_score, recall_score,
                             f1_score, matthews_corrcoef)
from xgboost import XGBClassifier
import json
import os
import warnings
warnings.filterwarnings("ignore")

CLEAN = "data/enriched/enriched_clean.csv"
LABELS = "data/enriched/verified_labels.csv"
MODEL_DIR = "models"

os.makedirs(MODEL_DIR, exist_ok=True)

print("=" * 70)
print("  DeFi Sentinel — Train & Export Production Model")
print("=" * 70)

df = pd.read_csv(CLEAN, low_memory=False)
labels = pd.read_csv(LABELS)
df = df.merge(labels[["MINT", "LIQUIDITY_POOL_ADDRESS", "RUG_LABEL"]],
              on=["MINT", "LIQUIDITY_POOL_ADDRESS"], how="left", suffixes=("", "_vl"))

rug_mask = df["RUG_LABEL"].isin(["VERIFIED_RUG", "LIKELY_RUG"])
legit_mask = df["RUG_LABEL"] == "LIKELY_LEGIT"
labeled = df[rug_mask | legit_mask].copy()
labeled["IS_RUG"] = rug_mask[labeled.index].astype(int)
print(f"Labeled: {len(labeled):,} ({labeled['IS_RUG'].sum():,} rug, {(~labeled['IS_RUG'].astype(bool)).sum():,} legit)")

# ── POST-OUTCOME features to EXCLUDE ──
post_outcome = {
    "TOKEN_PRICE_USD", "derived_has_price",
    "TOTAL_REMOVED_LIQUIDITY", "REMOVED_RATIO", "ADD_TO_REMOVE_RATIO",
    "derived_liquidity_depth_ratio", "derived_avg_remove_size",
    "derived_remove_add_size_ratio", "derived_drain_speed_pct_per_hour",
    "derived_single_drain_flag",
    "LIFESPAN_H", "derived_pool_active_hours", "derived_events_per_hour",
    "NUM_LIQUIDITY_REMOVES",
}

exclude_ids = {"LIQUIDITY_POOL_ADDRESS", "MINT", "OWNER", "IS_RUG",
               "TOKEN_NAME", "TOKEN_SYMBOL", "MINT_AUTHORITY", "FREEZE_AUTHORITY",
               "JSON_URI_DOMAIN", "TOKEN_STANDARD", "TOKEN_PROGRAM", "TOKEN_PRICE_CURRENCY",
               "FIRST_POOL_ACTIVITY_TIMESTAMP", "LAST_POOL_ACTIVITY_TIMESTAMP",
               "LAST_SWAP_TIMESTAMP", "FIRST", "LAST",
               "gt_pool_name", "gt_pool_dex", "gt_pool_created",
               "RC_RISK_NAMES", "RC_TOKEN_TYPE", "RUG_LABEL", "RUG_LABEL_vl",
               "rc_top_risk", "rc_top_risk_level", "rc_detected_at"}

all_exclude = post_outcome | exclude_ids

features = [c for c in labeled.columns
            if c not in all_exclude
            and labeled[c].dtype in ["float64", "int64", "float32", "int32"]
            and not c.startswith("SIG_")
            and c not in ["RUG_SIGNALS", "RUG_SCORE"]]

print(f"Creation-time features: {len(features)}")

# ── Temporal split ──
labeled["_year"] = pd.to_datetime(labeled["FIRST"], errors="coerce").dt.year
train = labeled[labeled["_year"] < 2024].copy()
test = labeled[labeled["_year"] >= 2024].copy()
print(f"Split: train={len(train):,} (<2024), test={len(test):,} (2024+)")

X_train = train[features].copy()
y_train = train["IS_RUG"]
X_test = test[features].copy()
y_test = test["IS_RUG"]

# ── Train ──
print("Training XGBoost...")
model = XGBClassifier(
    n_estimators=300, max_depth=6, learning_rate=0.05,
    subsample=0.8, colsample_bytree=0.8,
    scale_pos_weight=len(y_train[y_train==0]) / max(len(y_train[y_train==1]), 1),
    eval_metric="auc", random_state=42, verbosity=0,
    tree_method="hist",
)
model.fit(X_train, y_train)

# ── Evaluate ──
y_prob = model.predict_proba(X_test)[:, 1]
y_pred = (y_prob >= 0.5).astype(int)

auc = roc_auc_score(y_test, y_prob)
prec = precision_score(y_test, y_pred, zero_division=0)
rec = recall_score(y_test, y_pred, zero_division=0)
f1 = f1_score(y_test, y_pred, zero_division=0)
mcc = matthews_corrcoef(y_test, y_pred)

print(f"\n  AUC={auc:.4f}  P={prec:.4f}  R={rec:.4f}  F1={f1:.4f}  MCC={mcc:.4f}")

# ── Find optimal threshold ──
from sklearn.metrics import precision_recall_curve
precisions, recalls, thresholds = precision_recall_curve(y_test, y_prob)
f1s = 2 * precisions * recalls / (precisions + recalls + 1e-10)
best_idx = np.argmax(f1s)
best_threshold = float(thresholds[best_idx])
print(f"  Optimal threshold: {best_threshold:.4f} (F1={f1s[best_idx]:.4f})")

# ── Export model ──
model.save_model(os.path.join(MODEL_DIR, "model.json"))
print(f"  Saved: {MODEL_DIR}/model.json")

# ── Export feature list ──
with open(os.path.join(MODEL_DIR, "feature_list.json"), "w") as f:
    json.dump(features, f, indent=2)
print(f"  Saved: {MODEL_DIR}/feature_list.json ({len(features)} features)")

# ── Export metadata ──
imp = dict(zip(features, [float(x) for x in model.feature_importances_]))
imp_sorted = sorted(imp.items(), key=lambda x: -x[1])

meta = {
    "model_version": "1.0.0",
    "algorithm": "XGBoost",
    "n_estimators": 300,
    "max_depth": 6,
    "training_samples": len(X_train),
    "test_samples": len(X_test),
    "metrics": {
        "auc_roc": round(auc, 4),
        "precision": round(prec, 4),
        "recall": round(rec, 4),
        "f1_score": round(f1, 4),
        "mcc": round(mcc, 4),
    },
    "threshold_default": 0.5,
    "threshold_optimal": round(best_threshold, 4),
    "features_count": len(features),
    "top_features": [{"name": n, "importance": round(v, 4)} for n, v in imp_sorted[:10]],
    "feature_sources": {
        feat: ("GoPlus" if feat.startswith("gp_") else
               "RugCheck" if feat.startswith(("RC_", "rc_")) else
               "GeckoTerminal" if feat.startswith("gt_") else
               "Derived" if feat.startswith("derived_") else
               "Helius/SolRPDS")
        for feat in features
    },
}

with open(os.path.join(MODEL_DIR, "model_meta.json"), "w") as f:
    json.dump(meta, f, indent=2)
print(f"  Saved: {MODEL_DIR}/model_meta.json")

# ── Summary ──
print(f"\n{'=' * 70}")
print(f"  ✅ Production model exported to {MODEL_DIR}/")
print(f"  Features: {len(features)}")
print(f"  AUC: {auc:.4f}")
print(f"  Top 3: {', '.join(n for n, _ in imp_sorted[:3])}")
print(f"{'=' * 70}")
