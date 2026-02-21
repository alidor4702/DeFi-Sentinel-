"""
Export lookup tables and feature defaults for the production API.
These are computed from the training data and used by the live inference pipeline.
"""
import pandas as pd
import numpy as np
import json
import os

CLEAN = "data/enriched/enriched_clean.csv"
LABELS = "data/enriched/verified_labels.csv"
MODEL_DIR = "models"

print("Exporting lookup tables...")

df = pd.read_csv(CLEAN, low_memory=False)
labels = pd.read_csv(LABELS)
df = df.merge(labels[["MINT", "LIQUIDITY_POOL_ADDRESS", "RUG_LABEL"]],
              on=["MINT", "LIQUIDITY_POOL_ADDRESS"], how="left", suffixes=("", "_vl"))

labeled = df[df["RUG_LABEL"].isin(["VERIFIED_RUG", "LIKELY_RUG", "LIKELY_LEGIT"])].copy()
labeled["IS_RUG"] = labeled["RUG_LABEL"].isin(["VERIFIED_RUG", "LIKELY_RUG"]).astype(int)

# ── URI domain rug rates ──
if "JSON_URI_DOMAIN" in labeled.columns:
    uri_rates = labeled.groupby("JSON_URI_DOMAIN")["IS_RUG"].agg(["mean", "count"])
    # Only keep domains with ≥5 samples
    uri_rates = uri_rates[uri_rates["count"] >= 5]
    uri_domain_rug_rate = uri_rates["mean"].to_dict()
    default_uri_rate = float(labeled["IS_RUG"].mean())
else:
    uri_domain_rug_rate = {}
    default_uri_rate = 0.5

# ── Token standard rug rates ──
if "TOKEN_STANDARD" in labeled.columns:
    std_rates = labeled.groupby("TOKEN_STANDARD")["IS_RUG"].agg(["mean", "count"])
    std_rates = std_rates[std_rates["count"] >= 5]
    token_std_rug_rate = std_rates["mean"].to_dict()
    default_std_rate = float(labeled["IS_RUG"].mean())
else:
    token_std_rug_rate = {}
    default_std_rate = 0.5

# ── Feature medians (for filling missing values in live inference) ──
with open(os.path.join(MODEL_DIR, "feature_list.json")) as f:
    features = json.load(f)

feature_medians = {}
for feat in features:
    if feat in df.columns and df[feat].dtype in ["float64", "int64", "float32", "int32"]:
        med = df[feat].median()
        feature_medians[feat] = float(med) if pd.notna(med) else 0.0

lookups = {
    "uri_domain_rug_rate": uri_domain_rug_rate,
    "default_uri_rate": default_uri_rate,
    "token_std_rug_rate": token_std_rug_rate,
    "default_std_rate": default_std_rate,
    "feature_medians": feature_medians,
}

out_path = os.path.join(MODEL_DIR, "lookups.json")
with open(out_path, "w") as f:
    json.dump(lookups, f, indent=2, default=str)
print(f"Saved: {out_path}")
print(f"  URI domains: {len(uri_domain_rug_rate)}")
print(f"  Token standards: {len(token_std_rug_rate)}")
print(f"  Feature medians: {len(feature_medians)}")
print("Done!")
