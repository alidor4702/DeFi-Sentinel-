# Requirements: pandas scikit-learn joblib matplotlib seaborn numpy
# Usage: python train_solrpds.py --data_dir ./dataset --out_dir ./output
#
# SolRPDS — Solana Rug Pull Detection Training Script
# Paper: "SolRPDS: A Dataset for Analyzing Rug Pulls in Solana DeFi" (CODASPY 2025)
# Reproduces Table 4: AdaBoost ~97.6%, RF ~97.4%

import os
import sys
import glob
import argparse
import warnings

# Suppress sklearn and convergence warnings
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
os.environ["PYTHONWARNINGS"] = "ignore"

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
from joblib import dump

from sklearn.ensemble import RandomForestClassifier, AdaBoostClassifier
from sklearn.metrics import (
    roc_auc_score,
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    matthews_corrcoef,
    confusion_matrix,
)
from sklearn.model_selection import train_test_split
from sklearn.feature_selection import mutual_info_classif
from sklearn.preprocessing import LabelEncoder


# ──────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────
def parse_args():
    parser = argparse.ArgumentParser(
        description="Train rug-pull detection models on the SolRPDS dataset."
    )
    parser.add_argument(
        "--data_dir",
        type=str,
        default="./dataset",
        help="Path to folder containing SolRPDS CSV files (default: ./dataset)",
    )
    parser.add_argument(
        "--out_dir",
        type=str,
        default="./output",
        help="Path to save models and plots (default: ./output)",
    )
    parser.add_argument(
        "--year_train",
        type=int,
        default=2022,
        help="Year used for the training set (default: 2022)",
    )
    parser.add_argument(
        "--year_test",
        type=int,
        default=2021,
        help="Year used for the test set (default: 2021)",
    )
    return parser.parse_args()


# ──────────────────────────────────────────────────────────────────────
# LOAD
# ──────────────────────────────────────────────────────────────────────
def load_data(data_dir: str) -> pd.DataFrame:
    """Load and concatenate every CSV found under *data_dir*."""
    csv_files = sorted(
        glob.glob(os.path.join(data_dir, "**", "*.csv"), recursive=True)
    )
    if not csv_files:
        sys.exit(f"[ERROR] No CSV files found in '{data_dir}'. Check --data_dir.")

    print(f"[LOAD] Found {len(csv_files)} CSV file(s) in '{data_dir}':")
    frames = []
    for f in csv_files:
        print(f"       • {os.path.basename(f)}")
        try:
            df = pd.read_csv(f, low_memory=False)
            frames.append(df)
        except Exception as exc:
            print(f"       ⚠ skipped ({exc})")
    if not frames:
        sys.exit("[ERROR] Could not read any CSV files.")

    data = pd.concat(frames, ignore_index=True)
    print(f"[LOAD] Combined shape: {data.shape}")
    return data


# ──────────────────────────────────────────────────────────────────────
# FEATURE ENGINEERING
# ──────────────────────────────────────────────────────────────────────

# Columns expected from Table 1 of the paper
TARGET = "INACTIVITY_STATUS"

BASE_FEATURES = [
    "TOTAL_ADDED_LIQUIDITY",
    "TOTAL_REMOVED_LIQUIDITY",
    "NUM_LIQUIDITY_ADDS",
    "NUM_LIQUIDITY_REMOVES",
    "ADD_TO_REMOVE_RATIO",
]

TIMESTAMP_COLS = [
    "FIRST_POOL_ACTIVITY_TIMESTAMP",
    "LAST_POOL_ACTIVITY_TIMESTAMP",
    "LAST_SWAP_TIMESTAMP",
]


def _safe_col(df: pd.DataFrame, col: str) -> bool:
    """Return True if *col* exists in df, else warn."""
    if col in df.columns:
        return True
    print(f"       ⚠ Column '{col}' not found — skipping derived features that need it.")
    return False


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add derived features to the dataframe (in-place copy)."""
    df = df.copy()

    # --- Ensure base numeric columns are actually numeric ----------------
    for col in BASE_FEATURES:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # --- Net liquidity & removed ratio -----------------------------------
    if _safe_col(df, "TOTAL_ADDED_LIQUIDITY") and _safe_col(df, "TOTAL_REMOVED_LIQUIDITY"):
        df["LIQUIDITY_NET"] = df["TOTAL_ADDED_LIQUIDITY"] - df["TOTAL_REMOVED_LIQUIDITY"]
        df["REMOVED_RATIO"] = df["TOTAL_REMOVED_LIQUIDITY"] / (
            df["TOTAL_ADDED_LIQUIDITY"] + 1e-9
        )

    # --- Log-transformed features ----------------------------------------
    log_map = {
        "LOG_TOTAL_ADDED": "TOTAL_ADDED_LIQUIDITY",
        "LOG_TOTAL_REMOVED": "TOTAL_REMOVED_LIQUIDITY",
        "LOG_NUM_ADDS": "NUM_LIQUIDITY_ADDS",
        "LOG_NUM_REMOVES": "NUM_LIQUIDITY_REMOVES",
    }
    for new_col, src_col in log_map.items():
        if _safe_col(df, src_col):
            df[new_col] = np.log1p(df[src_col].fillna(0).clip(lower=0))

    # --- Timestamp-derived features --------------------------------------
    for tc in TIMESTAMP_COLS:
        if tc in df.columns:
            df[tc] = pd.to_datetime(df[tc], errors="coerce")

    if (
        _safe_col(df, "LAST_POOL_ACTIVITY_TIMESTAMP")
        and _safe_col(df, "FIRST_POOL_ACTIVITY_TIMESTAMP")
    ):
        delta = df["LAST_POOL_ACTIVITY_TIMESTAMP"] - df["FIRST_POOL_ACTIVITY_TIMESTAMP"]
        df["DURATION_DAYS"] = delta.dt.total_seconds() / 86400.0

    if (
        _safe_col(df, "LAST_SWAP_TIMESTAMP")
        and _safe_col(df, "LAST_POOL_ACTIVITY_TIMESTAMP")
    ):
        delta = df["LAST_SWAP_TIMESTAMP"] - df["LAST_POOL_ACTIVITY_TIMESTAMP"]
        df["SWAP_TO_LAST_ACTIVITY_DAYS"] = delta.dt.total_seconds() / 86400.0

    return df


# ──────────────────────────────────────────────────────────────────────
# SPLIT
# ──────────────────────────────────────────────────────────────────────
def split_by_year(df, year_train, year_test):
    """
    Split into train/test by year derived from FIRST_POOL_ACTIVITY_TIMESTAMP.
    Falls back to stratified 80/20 if timestamps are missing.
    """
    ts_col = "FIRST_POOL_ACTIVITY_TIMESTAMP"
    if ts_col in df.columns and df[ts_col].notna().sum() > 0:
        df["_year"] = pd.to_datetime(df[ts_col], errors="coerce").dt.year
        train_mask = df["_year"] == year_train
        test_mask = df["_year"] == year_test

        if train_mask.sum() > 0 and test_mask.sum() > 0:
            print(
                f"[SPLIT] Year-based: train={year_train} ({train_mask.sum()} rows), "
                f"test={year_test} ({test_mask.sum()} rows)"
            )
            train_df = df.loc[train_mask].copy()
            test_df = df.loc[test_mask].copy()
            train_df.drop(columns="_year", inplace=True, errors="ignore")
            test_df.drop(columns="_year", inplace=True, errors="ignore")
            df.drop(columns="_year", inplace=True, errors="ignore")
            return train_df, test_df
        else:
            print(
                f"[SPLIT] ⚠ Not enough data for year {year_train}/{year_test}. "
                "Falling back to 80/20 stratified split."
            )
            df.drop(columns="_year", inplace=True, errors="ignore")
    else:
        print("[SPLIT] ⚠ Timestamp column missing or all NaT. Falling back to 80/20 stratified split.")

    train_df, test_df = train_test_split(
        df, test_size=0.2, stratify=df[TARGET], random_state=42
    )
    print(f"[SPLIT] Stratified 80/20: train={len(train_df)}, test={len(test_df)}")
    return train_df, test_df


# ──────────────────────────────────────────────────────────────────────
# FEATURE SELECTION (mutual information)
# ──────────────────────────────────────────────────────────────────────
def select_features(X_train, y_train, feature_names):
    """Rank features with mutual_info_classif; drop zero-importance ones."""
    mi = mutual_info_classif(X_train, y_train, random_state=42, n_neighbors=5)
    mi_series = pd.Series(mi, index=feature_names).sort_values(ascending=False)

    print("\n[FEATURE SELECTION] Mutual Information scores:")
    for fname, score in mi_series.items():
        tag = "  ✗ DROPPED" if score == 0.0 else ""
        print(f"       {fname:35s} {score:.4f}{tag}")

    keep = mi_series[mi_series > 0].index.tolist()
    if not keep:
        print("       ⚠ All MI scores are zero — keeping all features.")
        keep = feature_names
    return keep, mi_series


# ──────────────────────────────────────────────────────────────────────
# TRAIN
# ──────────────────────────────────────────────────────────────────────
def get_models():
    """Return dict of model name → estimator (Table 4 of the paper)."""
    return {
        "RandomForest": RandomForestClassifier(
            n_estimators=200,
            n_jobs=-1,
            class_weight="balanced",
            random_state=42,
        ),
        "AdaBoost": AdaBoostClassifier(
            n_estimators=200,
            learning_rate=0.5,
            algorithm="SAMME",
            random_state=42,
        ),
    }


# ──────────────────────────────────────────────────────────────────────
# EVALUATE
# ──────────────────────────────────────────────────────────────────────
def evaluate(model, X_test, y_test):
    """Compute AUC, ACC, F1, Precision, Recall, MCC."""
    y_pred = model.predict(X_test)
    # For AUC we need probabilities or decision_function
    if hasattr(model, "predict_proba"):
        y_prob = model.predict_proba(X_test)[:, 1]
    elif hasattr(model, "decision_function"):
        y_prob = model.decision_function(X_test)
    else:
        y_prob = y_pred.astype(float)

    metrics = {
        "AUC": roc_auc_score(y_test, y_prob),
        "ACC": accuracy_score(y_test, y_pred),
        "F1 (weighted)": f1_score(y_test, y_pred, average="weighted", zero_division=0),
        "Precision (weighted)": precision_score(
            y_test, y_pred, average="weighted", zero_division=0
        ),
        "Recall (weighted)": recall_score(
            y_test, y_pred, average="weighted", zero_division=0
        ),
        "MCC": matthews_corrcoef(y_test, y_pred),
    }
    cm = confusion_matrix(y_test, y_pred)
    return metrics, cm, y_pred


# ──────────────────────────────────────────────────────────────────────
# SAVE — plots & artefacts
# ──────────────────────────────────────────────────────────────────────
def save_confusion_matrix(cm, model_name, out_dir):
    fig, ax = plt.subplots(figsize=(5, 4))
    sns.heatmap(
        cm,
        annot=True,
        fmt="d",
        cmap="Blues",
        xticklabels=["Active (0)", "Inactive (1)"],
        yticklabels=["Active (0)", "Inactive (1)"],
        ax=ax,
    )
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    ax.set_title(f"Confusion Matrix — {model_name}")
    path = os.path.join(out_dir, f"confusion_matrix_{model_name.lower()}.png")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"       Saved {path}")


def save_feature_importance(model, feature_names, model_name, out_dir):
    if hasattr(model, "feature_importances_"):
        importances = model.feature_importances_
    else:
        print(f"       ⚠ {model_name} has no feature_importances_ — skipping plot.")
        return None

    imp_df = (
        pd.DataFrame({"feature": feature_names, "importance": importances})
        .sort_values("importance", ascending=True)
    )

    fig, ax = plt.subplots(figsize=(7, max(4, len(feature_names) * 0.35)))
    ax.barh(imp_df["feature"], imp_df["importance"], color="steelblue")
    ax.set_xlabel("Importance")
    ax.set_title(f"Feature Importance — {model_name}")
    fig.tight_layout()
    path = os.path.join(out_dir, f"feature_importance_{model_name.lower()}.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"       Saved {path}")
    return imp_df


# ──────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────
def main():
    args = parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    # ── LOAD ─────────────────────────────────────────────────────────
    df = load_data(args.data_dir)

    # Normalise column names (strip whitespace, uppercase)
    df.columns = [c.strip().upper().replace(" ", "_") for c in df.columns]

    # Check for target column
    if TARGET not in df.columns:
        sys.exit(f"[ERROR] Target column '{TARGET}' not found. Available: {list(df.columns)}")

    # Coerce target to int (handle bool / string / float)
    df[TARGET] = (
        df[TARGET]
        .astype(str)
        .str.strip()
        .str.upper()
        .map(lambda v: 1 if v in ("1", "TRUE", "YES", "INACTIVE") else 0)
    )
    print(f"[LOAD] Target distribution:\n{df[TARGET].value_counts().to_string()}\n")

    # ── FEATURE ENGINEERING ──────────────────────────────────────────
    print("[FEATURES] Engineering derived features …")
    df = engineer_features(df)

    # Collect all candidate feature columns
    derived = [
        "LIQUIDITY_NET",
        "REMOVED_RATIO",
        "LOG_TOTAL_ADDED",
        "LOG_TOTAL_REMOVED",
        "LOG_NUM_ADDS",
        "LOG_NUM_REMOVES",
        "DURATION_DAYS",
        "SWAP_TO_LAST_ACTIVITY_DAYS",
    ]
    all_features = [c for c in BASE_FEATURES + derived if c in df.columns]
    print(f"[FEATURES] Candidate features ({len(all_features)}): {all_features}\n")

    # ── SPLIT ────────────────────────────────────────────────────────
    train_df, test_df = split_by_year(df, args.year_train, args.year_test)

    # Drop rows where target is NaN
    train_df = train_df.dropna(subset=[TARGET])
    test_df = test_df.dropna(subset=[TARGET])

    # Fill NaN features with 0 (safe default for counts / ratios)
    train_df[all_features] = train_df[all_features].fillna(0)
    test_df[all_features] = test_df[all_features].fillna(0)

    X_train = train_df[all_features].values
    y_train = train_df[TARGET].values.astype(int)
    X_test = test_df[all_features].values
    y_test = test_df[TARGET].values.astype(int)

    # ── Class balance ────────────────────────────────────────────────
    print("\n[CLASS BALANCE]")
    for label, (X, y) in {"Train": (X_train, y_train), "Test": (X_test, y_test)}.items():
        n0 = (y == 0).sum()
        n1 = (y == 1).sum()
        print(f"  {label:5s}  — Active (0): {n0:>7,}  |  Inactive (1): {n1:>7,}  |  Total: {len(y):>7,}  |  %Inactive: {100*n1/max(len(y),1):.1f}%")

    # ── FEATURE SELECTION ────────────────────────────────────────────
    keep_features, mi_scores = select_features(X_train, y_train, all_features)

    # Re-slice to kept features
    keep_idx = [all_features.index(f) for f in keep_features]
    X_train = X_train[:, keep_idx]
    X_test = X_test[:, keep_idx]
    print(f"\n[FEATURES] Using {len(keep_features)} features after MI selection.\n")

    # ── TRAIN & EVALUATE ─────────────────────────────────────────────
    models = get_models()
    results = {}
    importance_frames = []

    for name, model in models.items():
        print(f"[TRAIN] Fitting {name} …")
        model.fit(X_train, y_train)

        metrics, cm, y_pred = evaluate(model, X_test, y_test)
        results[name] = metrics

        print(f"[EVAL]  {name}:")
        for mname, mval in metrics.items():
            print(f"         {mname:22s} {mval:.4f}")

        # Save model
        model_path = os.path.join(args.out_dir, f"{name.lower()}_model.joblib")
        dump(model, model_path)
        print(f"       Saved {model_path}")

        # Save confusion matrix
        save_confusion_matrix(cm, name, args.out_dir)

        # Save feature importance chart
        imp_df = save_feature_importance(model, keep_features, name, args.out_dir)
        if imp_df is not None:
            imp_df["model"] = name
            importance_frames.append(imp_df)

        print()

    # ── Save combined feature_importances.csv ────────────────────────
    if importance_frames:
        combined_imp = pd.concat(importance_frames, ignore_index=True)
        imp_csv_path = os.path.join(args.out_dir, "feature_importances.csv")
        combined_imp.to_csv(imp_csv_path, index=False)
        print(f"[SAVE] Feature importances → {imp_csv_path}")

    # ── RESULTS TABLE ────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print(" RESULTS  (cf. Table 4 of the SolRPDS paper)")
    print("=" * 80)
    res_df = pd.DataFrame(results).T
    res_df.index.name = "Model"
    # Format as percentages (except MCC which is [-1, 1])
    fmt = res_df.copy()
    for c in fmt.columns:
        if c == "MCC":
            fmt[c] = fmt[c].map(lambda v: f"{v:.4f}")
        else:
            fmt[c] = fmt[c].map(lambda v: f"{v*100:.2f}%")
    print(fmt.to_string())
    print("=" * 80)

    # Save results table as CSV too
    res_csv = os.path.join(args.out_dir, "results.csv")
    res_df.to_csv(res_csv)
    print(f"[SAVE] Results table → {res_csv}")

    print("\n✓ Done. All artefacts saved to:", args.out_dir)


if __name__ == "__main__":
    main()
