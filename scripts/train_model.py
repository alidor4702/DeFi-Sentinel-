"""
train_model.py — Train XGBoost rug-pull detector on multi-source enriched data
================================================================================

Uses ALL enriched features from 5 data sources:
  1. SolRPDS base features (liquidity, swaps, timestamps)
  2. Helius DAS (metadata, supply, authority, creator)
  3. RugCheck (risk score, top holders, LP providers)
  4. GeckoTerminal (price, volume, TVL, pool activity)
  5. GoPlus Security (holder concentration, TVL, LP locks)

Temporal split: Train on 2021-2023, test on 2024 (forward validation).
This is what a quant firm expects — "does it generalize to unseen future data?"

Outputs:
  models/xgboost_model.joblib          — serialized model for backend
  models/feature_importance.csv        — ranked feature importances
  data/figures/roc_curve.png           — ROC curve
  data/figures/precision_recall.png    — Precision-Recall curve
  data/figures/confusion_matrix.png    — Confusion matrix heatmap
  data/figures/feature_importance.png  — Top 30 features bar chart
  data/figures/shap_summary.png        — SHAP beeswarm plot (if shap installed)
  data/figures/source_importance.png   — Importance by data source

Usage:
  python scripts/train_model.py                          # default
  python scripts/train_model.py --input enriched_final.csv
  python scripts/train_model.py --no-shap                # skip SHAP (faster)
"""

import os
import sys
import warnings
import argparse
from datetime import datetime

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
from joblib import dump

from sklearn.metrics import (
    roc_auc_score, roc_curve, auc,
    precision_recall_curve, average_precision_score,
    accuracy_score, f1_score, precision_score, recall_score,
    matthews_corrcoef, confusion_matrix, classification_report,
)
from sklearn.model_selection import train_test_split

try:
    from xgboost import XGBClassifier
except ImportError:
    sys.exit("[ERROR] pip install xgboost")


# ── Config ──────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data", "enriched")
FIG_DIR = os.path.join(BASE_DIR, "data", "figures")
MODEL_DIR = os.path.join(BASE_DIR, "models")

# Features to EXCLUDE from training (identifiers, targets, leakage)
EXCLUDE_COLS = {
    # Identifiers
    "LIQUIDITY_POOL_ADDRESS", "MINT", "TOKEN_NAME", "TOKEN_SYMBOL",
    "FIRST_POOL_ACTIVITY_TIMESTAMP", "LAST_POOL_ACTIVITY_TIMESTAMP",
    "LAST_SWAP_TIMESTAMP", "FIRST", "LAST",
    # Target and label columns (leakage)
    "INACTIVITY_STATUS", "RUG_LABEL", "LABEL_TIER",
    "RUG_SCORE", "RUG_SIGNALS",
    # Signal columns (used to BUILD labels, would be leakage)
    "SIG_INACTIVE", "SIG_NO_PRICE", "SIG_NO_METADATA", "SIG_NO_IMAGE",
    "SIG_MUTABLE", "SIG_DRAINED", "SIG_SHORT_LIFE", "SIG_FEW_TXN", "SIG_NO_NAME",
    # String/object columns from enrichment
    "rc_top_risk", "rc_top_risk_level", "rc_detected_at",
    "rc_freeze_authority", "rc_mint_authority",
    "gt_pool_name", "gt_pool_dex", "gt_pool_created",
    "gp_token_name", "gp_token_symbol", "gp_freeze_authority",
    "gp_default_account_state",
    # Helius string columns
    "TOKEN_PROGRAM", "JSON_URI_DOMAIN", "METADATA_STANDARD",
    # Internal helper columns
    "_sort", "_year",
}

# Map data source prefix to label for source importance chart
SOURCE_MAP = {
    "rc_": "RugCheck",
    "gt_": "GeckoTerminal",
    "gp_": "GoPlus",
    # Helius features don't have a prefix — identified by name
}

HELIUS_FEATURES = {
    "HAS_METADATA", "HAS_IMAGE", "IS_MUTABLE", "MINT_AUTHORITY_ACTIVE",
    "FREEZE_AUTHORITY_ACTIVE", "TOKEN_PRICE_USD", "TOKEN_SUPPLY",
    "TOKEN_DECIMALS", "IS_BURNT", "NUM_CREATORS", "CREATOR_VERIFIED",
    "HAS_JSON_URI", "TOKEN_STANDARD_ENCODED", "SUPPLY_LOG",
    "PRICE_LOG", "SUPPLY_PRICE_RATIO",
}

SOLRPDS_FEATURES = {
    "TOTAL_ADDED_LIQUIDITY", "TOTAL_REMOVED_LIQUIDITY",
    "NUM_LIQUIDITY_ADDS", "NUM_LIQUIDITY_REMOVES",
    "ADD_TO_REMOVE_RATIO", "LIQUIDITY_NET", "REMOVED_RATIO",
    "LOG_TOTAL_ADDED", "LOG_TOTAL_REMOVED", "LOG_NUM_ADDS",
    "LOG_NUM_REMOVES", "DURATION_DAYS", "SWAP_TO_LAST_ACTIVITY_DAYS",
    "LIFESPAN_H",
}


def get_source(col):
    """Map a feature column to its data source."""
    for prefix, source in SOURCE_MAP.items():
        if col.startswith(prefix):
            return source
    if col in HELIUS_FEATURES or col.startswith("TOKEN_") or col.startswith("HAS_") or col.startswith("IS_"):
        return "Helius"
    if col in SOLRPDS_FEATURES:
        return "SolRPDS"
    return "Derived"


def parse_args():
    p = argparse.ArgumentParser(description="Train XGBoost on enriched data")
    p.add_argument("--input", default="enriched_final.csv", help="Input CSV in data/enriched/")
    p.add_argument("--target", default="INACTIVITY_STATUS", help="Target column")
    p.add_argument("--no-shap", action="store_true", help="Skip SHAP analysis")
    p.add_argument("--test-year", type=int, default=2024, help="Hold-out year for temporal split")
    return p.parse_args()


def load_and_prepare(args):
    """Load enriched CSV, create binary target, engineer features."""
    path = os.path.join(DATA_DIR, args.input)
    if not os.path.exists(path):
        sys.exit(f"[ERROR] Not found: {path}")

    print(f"Loading {path}...")
    df = pd.read_csv(path, low_memory=False)
    print(f"  {len(df):,} rows × {len(df.columns)} columns")

    # Parse timestamps for temporal split
    ts_col = "FIRST_POOL_ACTIVITY_TIMESTAMP"
    if ts_col in df.columns:
        df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce")
        df["_year"] = df[ts_col].dt.year
    else:
        print("  WARNING: No timestamp column — will use random split")

    # Binary target: Inactive=1 (rug), Active=0 (legit)
    if args.target in df.columns:
        df["TARGET"] = (
            df[args.target]
            .astype(str).str.strip().str.upper()
            .map(lambda v: 1 if v in ("1", "TRUE", "INACTIVE") else 0)
        )
    else:
        sys.exit(f"[ERROR] Target column '{args.target}' not found")

    print(f"  Target distribution: {df['TARGET'].value_counts().to_dict()}")

    # Engineer derived features from base columns
    if "TOTAL_ADDED_LIQUIDITY" in df.columns and "TOTAL_REMOVED_LIQUIDITY" in df.columns:
        df["LIQUIDITY_NET"] = df["TOTAL_ADDED_LIQUIDITY"] - df["TOTAL_REMOVED_LIQUIDITY"]
        df["REMOVED_RATIO"] = df["TOTAL_REMOVED_LIQUIDITY"] / (df["TOTAL_ADDED_LIQUIDITY"] + 1e-9)

    for src, dst in [("TOTAL_ADDED_LIQUIDITY", "LOG_TOTAL_ADDED"),
                     ("TOTAL_REMOVED_LIQUIDITY", "LOG_TOTAL_REMOVED"),
                     ("NUM_LIQUIDITY_ADDS", "LOG_NUM_ADDS"),
                     ("NUM_LIQUIDITY_REMOVES", "LOG_NUM_REMOVES")]:
        if src in df.columns:
            df[dst] = np.log1p(pd.to_numeric(df[src], errors="coerce").fillna(0).clip(lower=0))

    # Lifespan
    if "FIRST_POOL_ACTIVITY_TIMESTAMP" in df.columns and "LAST_POOL_ACTIVITY_TIMESTAMP" in df.columns:
        first = pd.to_datetime(df["FIRST_POOL_ACTIVITY_TIMESTAMP"], errors="coerce")
        last = pd.to_datetime(df["LAST_POOL_ACTIVITY_TIMESTAMP"], errors="coerce")
        df["DURATION_DAYS"] = (last - first).dt.total_seconds() / 86400.0

    # Encode binary string columns as 0/1
    for col in ["gp_closable", "gp_balance_mutable", "gp_transfer_fee", "gp_non_transferable"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    return df


def select_features(df):
    """Select numeric features, excluding identifiers and leakage columns."""
    candidates = []
    for col in df.columns:
        if col in EXCLUDE_COLS or col == "TARGET" or col == "_year":
            continue
        # Only numeric columns
        if df[col].dtype in [np.float64, np.float32, np.int64, np.int32, np.bool_]:
            # Skip columns that are >95% NaN (useless)
            non_null_pct = df[col].notna().mean()
            if non_null_pct < 0.05:
                continue
            candidates.append(col)

    print(f"\n  Selected {len(candidates)} numeric features")
    return candidates


def temporal_split(df, features, test_year):
    """Split by time: train on everything before test_year, test on test_year."""
    if "_year" in df.columns and df["_year"].notna().sum() > 0:
        train_mask = df["_year"] < test_year
        test_mask = df["_year"] == test_year

        if train_mask.sum() > 100 and test_mask.sum() > 100:
            train_df = df[train_mask].copy()
            test_df = df[test_mask].copy()
            print(f"\n  Temporal split: train <{test_year} ({len(train_df):,} rows), "
                  f"test {test_year} ({len(test_df):,} rows)")

            # Show class balance per split
            for name, split_df in [("Train", train_df), ("Test", test_df)]:
                n0 = (split_df["TARGET"] == 0).sum()
                n1 = (split_df["TARGET"] == 1).sum()
                print(f"    {name}: Active={n0:,} | Inactive(rug)={n1:,} | rug%={n1/(n0+n1)*100:.1f}%")

            X_train = train_df[features].fillna(0).values
            y_train = train_df["TARGET"].values
            X_test = test_df[features].fillna(0).values
            y_test = test_df["TARGET"].values
            return X_train, X_test, y_train, y_test, "temporal"

    # Fallback: stratified random split
    print("\n  Fallback: stratified 80/20 random split")
    X = df[features].fillna(0).values
    y = df["TARGET"].values
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )
    return X_train, X_test, y_train, y_test, "stratified"


def train_xgboost(X_train, y_train):
    """Train XGBoost with good defaults for imbalanced tabular data."""
    n_pos = (y_train == 1).sum()
    n_neg = (y_train == 0).sum()
    scale = n_neg / max(n_pos, 1)

    model = XGBClassifier(
        n_estimators=500,
        max_depth=8,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=scale,
        eval_metric="aucpr",
        random_state=42,
        n_jobs=-1,
        tree_method="hist",
        verbosity=0,
    )

    print(f"\n  Training XGBoost (500 trees, depth=8, scale_pos_weight={scale:.2f})...")
    model.fit(X_train, y_train)
    return model


def evaluate_model(model, X_test, y_test, features):
    """Full evaluation with all metrics."""
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]

    metrics = {
        "AUC-ROC": roc_auc_score(y_test, y_prob),
        "AUC-PR": average_precision_score(y_test, y_prob),
        "Accuracy": accuracy_score(y_test, y_pred),
        "F1 (weighted)": f1_score(y_test, y_pred, average="weighted"),
        "Precision (rug)": precision_score(y_test, y_pred, pos_label=1, zero_division=0),
        "Recall (rug)": recall_score(y_test, y_pred, pos_label=1, zero_division=0),
        "MCC": matthews_corrcoef(y_test, y_pred),
    }

    print("\n" + "=" * 60)
    print("  MODEL PERFORMANCE")
    print("=" * 60)
    for name, val in metrics.items():
        print(f"    {name:25s} {val:.4f}")

    print(f"\n  Classification Report:")
    print(classification_report(y_test, y_pred, target_names=["Active (legit)", "Inactive (rug)"]))

    cm = confusion_matrix(y_test, y_pred)
    return metrics, cm, y_pred, y_prob


def save_plots(model, features, y_test, y_prob, y_pred, cm):
    """Generate all evaluation plots."""
    os.makedirs(FIG_DIR, exist_ok=True)

    # 1. ROC Curve
    fpr, tpr, _ = roc_curve(y_test, y_prob)
    roc_auc = auc(fpr, tpr)
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.plot(fpr, tpr, color="#2563eb", lw=2, label=f"XGBoost (AUC = {roc_auc:.4f})")
    ax.plot([0, 1], [0, 1], "k--", lw=1, alpha=0.5)
    ax.set_xlabel("False Positive Rate", fontsize=12)
    ax.set_ylabel("True Positive Rate", fontsize=12)
    ax.set_title("ROC Curve — Rug Pull Detection", fontsize=14, fontweight="bold")
    ax.legend(fontsize=11)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "roc_curve.png"), dpi=150)
    plt.close(fig)
    print(f"  Saved {FIG_DIR}/roc_curve.png")

    # 2. Precision-Recall Curve
    prec, rec, _ = precision_recall_curve(y_test, y_prob)
    ap = average_precision_score(y_test, y_prob)
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.plot(rec, prec, color="#dc2626", lw=2, label=f"XGBoost (AP = {ap:.4f})")
    ax.set_xlabel("Recall", fontsize=12)
    ax.set_ylabel("Precision", fontsize=12)
    ax.set_title("Precision-Recall Curve — Rug Pull Detection", fontsize=14, fontweight="bold")
    ax.legend(fontsize=11)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "precision_recall.png"), dpi=150)
    plt.close(fig)
    print(f"  Saved {FIG_DIR}/precision_recall.png")

    # 3. Confusion Matrix
    fig, ax = plt.subplots(figsize=(6, 5))
    sns.heatmap(cm, annot=True, fmt=",d", cmap="Blues",
                xticklabels=["Active", "Rug"],
                yticklabels=["Active", "Rug"], ax=ax,
                annot_kws={"size": 14})
    ax.set_xlabel("Predicted", fontsize=12)
    ax.set_ylabel("Actual", fontsize=12)
    ax.set_title("Confusion Matrix", fontsize=14, fontweight="bold")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "confusion_matrix.png"), dpi=150)
    plt.close(fig)
    print(f"  Saved {FIG_DIR}/confusion_matrix.png")

    # 4. Feature Importance (top 30)
    importances = model.feature_importances_
    imp_df = pd.DataFrame({"feature": features, "importance": importances})
    imp_df["source"] = imp_df["feature"].apply(get_source)
    imp_df = imp_df.sort_values("importance", ascending=False)

    # Save full CSV
    os.makedirs(MODEL_DIR, exist_ok=True)
    imp_df.to_csv(os.path.join(MODEL_DIR, "feature_importance.csv"), index=False)

    # Plot top 30
    top30 = imp_df.head(30).sort_values("importance", ascending=True)
    source_colors = {
        "SolRPDS": "#3b82f6",
        "Helius": "#10b981",
        "RugCheck": "#f59e0b",
        "GeckoTerminal": "#8b5cf6",
        "GoPlus": "#ef4444",
        "Derived": "#6b7280",
    }
    colors = [source_colors.get(s, "#6b7280") for s in top30["source"]]

    fig, ax = plt.subplots(figsize=(10, 9))
    bars = ax.barh(top30["feature"], top30["importance"], color=colors)
    ax.set_xlabel("Importance (gain)", fontsize=12)
    ax.set_title("Top 30 Features — XGBoost Rug Pull Detector", fontsize=14, fontweight="bold")

    # Legend for data sources
    from matplotlib.patches import Patch
    legend_elements = [Patch(facecolor=c, label=s) for s, c in source_colors.items()
                       if s in top30["source"].values]
    ax.legend(handles=legend_elements, loc="lower right", fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "feature_importance.png"), dpi=150)
    plt.close(fig)
    print(f"  Saved {FIG_DIR}/feature_importance.png")

    # 5. Source importance breakdown (pie/bar)
    source_imp = imp_df.groupby("source")["importance"].sum().sort_values(ascending=False)
    source_imp_pct = source_imp / source_imp.sum() * 100

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    # Bar chart
    bar_colors = [source_colors.get(s, "#6b7280") for s in source_imp.index]
    ax1.barh(source_imp.index, source_imp_pct.values, color=bar_colors)
    ax1.set_xlabel("% of Total Feature Importance", fontsize=12)
    ax1.set_title("Importance by Data Source", fontsize=14, fontweight="bold")
    for i, (v, s) in enumerate(zip(source_imp_pct.values, source_imp.index)):
        ax1.text(v + 0.5, i, f"{v:.1f}%", va="center", fontsize=11)

    # Feature count per source
    source_counts = imp_df.groupby("source").size()
    ax2.barh(source_counts.index, source_counts.values, color=[source_colors.get(s, "#6b7280") for s in source_counts.index])
    ax2.set_xlabel("Number of Features", fontsize=12)
    ax2.set_title("Features per Data Source", fontsize=14, fontweight="bold")
    for i, v in enumerate(source_counts.values):
        ax2.text(v + 0.3, i, str(v), va="center", fontsize=11)

    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "source_importance.png"), dpi=150)
    plt.close(fig)
    print(f"  Saved {FIG_DIR}/source_importance.png")

    return imp_df


def run_shap(model, X_test, features):
    """SHAP analysis for model explainability."""
    try:
        import shap
    except ImportError:
        print("\n  [SHAP] shap not installed — pip install shap to enable")
        return

    print("\n  Computing SHAP values (this takes a minute)...")
    # Use a sample for speed
    n_sample = min(1000, len(X_test))
    idx = np.random.RandomState(42).choice(len(X_test), n_sample, replace=False)
    X_sample = X_test[idx]

    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_sample)

    # Summary plot
    fig = plt.figure(figsize=(12, 10))
    shap.summary_plot(shap_values, X_sample, feature_names=features, show=False, max_display=25)
    plt.title("SHAP Feature Impact — Top 25", fontsize=14, fontweight="bold")
    plt.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "shap_summary.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {FIG_DIR}/shap_summary.png")


def main():
    args = parse_args()
    os.makedirs(MODEL_DIR, exist_ok=True)
    os.makedirs(FIG_DIR, exist_ok=True)

    print("=" * 60)
    print(f"  DEFI SENTINEL — MODEL TRAINING")
    print(f"  {datetime.now():%Y-%m-%d %H:%M}")
    print("=" * 60)

    # Load
    df = load_and_prepare(args)

    # Feature selection
    features = select_features(df)

    # Split
    X_train, X_test, y_train, y_test, split_type = temporal_split(df, features, args.test_year)

    # Train
    model = train_xgboost(X_train, y_train)

    # Evaluate
    metrics, cm, y_pred, y_prob = evaluate_model(model, X_test, y_test, features)

    # Save model
    model_path = os.path.join(MODEL_DIR, "xgboost_model.joblib")
    dump(model, model_path)
    print(f"\n  Model saved: {model_path}")

    # Save metrics
    metrics_df = pd.DataFrame([metrics])
    metrics_df["split_type"] = split_type
    metrics_df["n_features"] = len(features)
    metrics_df["train_size"] = len(y_train)
    metrics_df["test_size"] = len(y_test)
    metrics_df.to_csv(os.path.join(MODEL_DIR, "metrics.csv"), index=False)

    # Plots
    print("\n  Generating plots...")
    imp_df = save_plots(model, features, y_test, y_prob, y_pred, cm)

    # SHAP
    if not args.no_shap:
        run_shap(model, X_test, features)

    # Summary
    print("\n" + "=" * 60)
    print("  TRAINING COMPLETE")
    print("=" * 60)
    print(f"  Features:  {len(features)} from {imp_df['source'].nunique()} data sources")
    print(f"  Split:     {split_type} (test year: {args.test_year})")
    print(f"  AUC-ROC:   {metrics['AUC-ROC']:.4f}")
    print(f"  AUC-PR:    {metrics['AUC-PR']:.4f}")
    print(f"  F1:        {metrics['F1 (weighted)']:.4f}")
    print(f"  MCC:       {metrics['MCC']:.4f}")
    print(f"\n  Top 5 features:")
    for _, row in imp_df.head(5).iterrows():
        print(f"    {row['feature']:35s} ({row['source']:12s}) {row['importance']:.4f}")
    print()
    print(f"  Artifacts: {MODEL_DIR}/")
    print(f"  Plots:     {FIG_DIR}/")
    print("=" * 60)


if __name__ == "__main__":
    main()
