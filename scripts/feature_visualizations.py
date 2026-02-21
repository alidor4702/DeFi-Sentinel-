"""
DeFi Sentinel — Feature Analysis Visualizations
Generates comprehensive plots for understanding the data.
"""
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
import seaborn as sns
import warnings
warnings.filterwarnings("ignore")

plt.rcParams.update({
    "figure.dpi": 150,
    "savefig.dpi": 150,
    "font.size": 11,
    "axes.titlesize": 13,
    "axes.labelsize": 11,
    "figure.facecolor": "#0d1117",
    "axes.facecolor": "#161b22",
    "text.color": "#c9d1d9",
    "axes.labelcolor": "#c9d1d9",
    "xtick.color": "#8b949e",
    "ytick.color": "#8b949e",
    "axes.edgecolor": "#30363d",
    "grid.color": "#21262d",
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.3,
})

COLORS = {
    "Helius": "#58a6ff",
    "GoPlus": "#f97583",
    "GeckoTerminal": "#56d364",
    "RugCheck": "#d2a8ff",
    "SolRPDS": "#f0883e",
    "Derived": "#8b949e",
    "Jupiter": "#79c0ff",
    "Creator Wallet": "#ffa657",
}
RUG_COLOR = "#f85149"
LEGIT_COLOR = "#3fb950"
ACCENT = "#58a6ff"

OUT = "data/figures"

# ── Load data ──
print("Loading data...")
df = pd.read_csv("data/enriched/enriched_final.csv")
labels = pd.read_csv("data/enriched/verified_labels.csv")
df = df.merge(labels[["MINT", "LIQUIDITY_POOL_ADDRESS", "RUG_LABEL"]],
              on=["MINT", "LIQUIDITY_POOL_ADDRESS"], how="left", suffixes=("", "_vl"))

rug_mask = df["RUG_LABEL"].isin(["VERIFIED_RUG", "LIKELY_RUG"])
legit_mask = df["RUG_LABEL"] == "LIKELY_LEGIT"
labeled = df[rug_mask | legit_mask].copy()
labeled["IS_RUG"] = rug_mask[labeled.index].astype(int)
n_rug = labeled["IS_RUG"].sum()
n_legit = len(labeled) - n_rug

print(f"Labeled: {len(labeled):,} rows ({n_rug:,} rug, {n_legit:,} legit)")

# ═══════════════════════════════════════════════════════════════
# PLOT 1: 82-Feature Spec Coverage Map
# ═══════════════════════════════════════════════════════════════
print("Plot 1: Feature coverage map...")

coverage = {
    "Helius\n(21)": (14, 7),
    "Creator\nWallet (6)": (0, 6),
    "RugCheck\n(18)": (8, 10),
    "Gecko\nTerminal (25)": (16, 9),
    "Jupiter\n(5)": (0, 5),
    "Derived\n(7)": (0, 7),
}

fig, ax = plt.subplots(figsize=(12, 5))
sources = list(coverage.keys())
have = [v[0] for v in coverage.values()]
miss = [v[1] for v in coverage.values()]
x = np.arange(len(sources))
w = 0.55

bars_have = ax.bar(x, have, w, label="✅ Available", color=LEGIT_COLOR, alpha=0.9, edgecolor="#30363d")
bars_miss = ax.bar(x, miss, w, bottom=have, label="❌ Missing", color=RUG_COLOR, alpha=0.7, edgecolor="#30363d")

for i, (h, m) in enumerate(zip(have, miss)):
    total = h + m
    pct = 100 * h / total if total > 0 else 0
    ax.text(i, total + 0.5, f"{h}/{total}\n({pct:.0f}%)", ha="center", va="bottom",
            fontsize=10, fontweight="bold", color="#c9d1d9")

ax.set_xticks(x)
ax.set_xticklabels(sources, fontsize=10)
ax.set_ylabel("Number of Features")
ax.set_title("82-Feature Live Spec — Coverage by Source", fontsize=15, fontweight="bold", pad=15)
ax.legend(loc="upper right", framealpha=0.8)
ax.set_ylim(0, 32)
ax.grid(axis="y", alpha=0.3)

# Add total box
total_have = sum(have)
total_miss = sum(miss)
ax.text(0.98, 0.95, f"TOTAL: {total_have}/82 ({100*total_have/82:.0f}%)",
        transform=ax.transAxes, ha="right", va="top", fontsize=12, fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.4", facecolor=ACCENT, alpha=0.3, edgecolor=ACCENT))

fig.savefig(f"{OUT}/feature_coverage_map.png")
plt.close()
print(f"  → {OUT}/feature_coverage_map.png")

# ═══════════════════════════════════════════════════════════════
# PLOT 2: Feature Correlation with Rug Label (Top 20)
# ═══════════════════════════════════════════════════════════════
print("Plot 2: Feature correlations...")

# Compute correlations
internal = {"LIQUIDITY_POOL_ADDRESS", "MINT", "LAST_SWAP_TX_ID", "INACTIVITY_STATUS",
            "RUG_LABEL", "RUG_LABEL_vl", "IS_RUG"}
signal_cols = {c for c in labeled.columns if c.startswith("SIG_") or c in
               ["RUG_SIGNALS", "RUG_SCORE", "FIRST", "LAST", "LIFESPAN_H", "REMOVED_RATIO"]}

corrs = []
for col in labeled.columns:
    if col in internal or col in signal_cols or col == "IS_RUG" or col.endswith("_vl"):
        continue
    if labeled[col].dtype not in ['float64', 'int64', 'float32', 'int32']:
        continue
    valid = labeled[[col, "IS_RUG"]].dropna()
    if len(valid) < 100:
        continue
    r = valid[col].corr(valid["IS_RUG"])
    if np.isnan(r):
        continue
    # source
    src = "GoPlus" if col.startswith("gp_") else \
          "GeckoTerminal" if col.startswith("gt_") else \
          "RugCheck" if col.startswith(("RC_", "rc_")) else \
          "SolRPDS" if col in ["TOTAL_ADDED_LIQUIDITY", "TOTAL_REMOVED_LIQUIDITY",
                                "NUM_LIQUIDITY_ADDS", "NUM_LIQUIDITY_REMOVES", "ADD_TO_REMOVE_RATIO"] else \
          "Helius"
    corrs.append({"feature": col, "corr": r, "abs_corr": abs(r), "source": src})

corr_df = pd.DataFrame(corrs).sort_values("abs_corr", ascending=False)

# Top 20 by absolute correlation
top = corr_df.head(20).iloc[::-1]  # reverse for horizontal bar

fig, ax = plt.subplots(figsize=(12, 9))
colors = [COLORS.get(s, "#8b949e") for s in top["source"]]
bars = ax.barh(range(len(top)), top["corr"], color=colors, edgecolor="#30363d", height=0.7)

ax.set_yticks(range(len(top)))
ax.set_yticklabels(top["feature"], fontsize=10)
ax.set_xlabel("Correlation with Rug Label (IS_RUG)")
ax.set_title("Top 20 Features by Correlation with Rug/Legit", fontsize=15, fontweight="bold", pad=15)
ax.axvline(0, color="#484f58", linewidth=1)
ax.grid(axis="x", alpha=0.3)

# Add value labels
for i, (val, feat) in enumerate(zip(top["corr"], top["feature"])):
    offset = -0.03 if val > 0 else 0.03
    ha = "right" if val > 0 else "left"
    ax.text(val + offset, i, f"{val:+.3f}", ha=ha, va="center", fontsize=9, fontweight="bold")

# Legend
patches = [mpatches.Patch(color=COLORS[s], label=s) for s in ["Helius", "GoPlus", "GeckoTerminal", "SolRPDS"]]
ax.legend(handles=patches, loc="lower right", framealpha=0.8, fontsize=10)

# Annotations
ax.text(0.02, 0.02, "← Legit tokens higher    |    Rug tokens higher →",
        transform=ax.transAxes, fontsize=9, alpha=0.7, style="italic")

fig.savefig(f"{OUT}/feature_correlations_top20.png")
plt.close()
print(f"  → {OUT}/feature_correlations_top20.png")

# ═══════════════════════════════════════════════════════════════
# PLOT 3: Rug vs Legit Distribution (Top 6 features)
# ═══════════════════════════════════════════════════════════════
print("Plot 3: Rug vs Legit distributions...")

top_features = [
    ("TOKEN_PRICE_USD", "Helius", True),
    ("HAS_JSON_URI", "Helius", False),
    ("gp_lp_count", "GoPlus", False),
    ("gp_top3_holder_pct", "GoPlus", False),
    ("TOKEN_SUPPLY", "Helius", True),
    ("HAS_METADATA", "Helius", False),
]

fig, axes = plt.subplots(2, 3, figsize=(18, 10))
fig.suptitle("Rug vs Legit — Distribution of Top Predictive Features",
             fontsize=16, fontweight="bold", y=1.02)

for idx, (feat, src, use_log) in enumerate(top_features):
    ax = axes[idx // 3][idx % 3]

    rug_data = labeled.loc[labeled["IS_RUG"] == 1, feat].dropna()
    legit_data = labeled.loc[labeled["IS_RUG"] == 0, feat].dropna()

    if len(rug_data) < 5 or len(legit_data) < 5:
        ax.text(0.5, 0.5, f"{feat}\n(insufficient data)", ha="center", va="center",
                transform=ax.transAxes, fontsize=12)
        continue

    nunique = labeled[feat].dropna().nunique()

    if nunique <= 3:
        # Bar chart for binary features
        rug_pct = rug_data.mean() * 100
        legit_pct = legit_data.mean() * 100
        x = [0, 1]
        ax.bar([0 - 0.15, 1 - 0.15], [100 - rug_pct, 100 - legit_pct], 0.28,
               label="= 0 (False)", color="#484f58", alpha=0.7, edgecolor="#30363d")
        ax.bar([0 + 0.15, 1 + 0.15], [rug_pct, legit_pct], 0.28,
               label="= 1 (True)", color=ACCENT, alpha=0.9, edgecolor="#30363d")
        ax.set_xticks([0, 1])
        ax.set_xticklabels(["Rug", "Legit"], fontsize=11)
        ax.set_ylabel("% of tokens")
        ax.text(0 + 0.15, rug_pct + 2, f"{rug_pct:.1f}%", ha="center", fontsize=9, fontweight="bold")
        ax.text(1 + 0.15, legit_pct + 2, f"{legit_pct:.1f}%", ha="center", fontsize=9, fontweight="bold")
        ax.legend(fontsize=8, loc="upper right")
    else:
        # Histogram for continuous
        if use_log:
            rug_plot = np.log10(rug_data.replace(0, np.nan).dropna().clip(lower=1e-15))
            legit_plot = np.log10(legit_data.replace(0, np.nan).dropna().clip(lower=1e-15))
            xlabel = f"log₁₀({feat})"
        else:
            rug_plot = rug_data
            legit_plot = legit_data
            xlabel = feat

        # Clip extreme outliers for visualization
        combined = pd.concat([rug_plot, legit_plot])
        lo, hi = combined.quantile(0.01), combined.quantile(0.99)
        bins = np.linspace(lo, hi, 40)

        ax.hist(rug_plot.clip(lo, hi), bins=bins, alpha=0.7, color=RUG_COLOR, label=f"Rug (n={len(rug_data):,})", density=True)
        ax.hist(legit_plot.clip(lo, hi), bins=bins, alpha=0.6, color=LEGIT_COLOR, label=f"Legit (n={len(legit_data):,})", density=True)
        ax.set_xlabel(xlabel)
        ax.set_ylabel("Density")
        ax.legend(fontsize=8, loc="upper right")

    # Correlation text
    valid = labeled[[feat, "IS_RUG"]].dropna()
    r = valid[feat].corr(valid["IS_RUG"])
    ax.set_title(f"{feat}  (r = {r:+.3f})", fontsize=12, fontweight="bold",
                 color=COLORS.get(src, "#c9d1d9"))
    ax.grid(alpha=0.2)

fig.tight_layout()
fig.savefig(f"{OUT}/feature_distributions_top6.png")
plt.close()
print(f"  → {OUT}/feature_distributions_top6.png")

# ═══════════════════════════════════════════════════════════════
# PLOT 4: Source Importance (from model + correlation analysis)
# ═══════════════════════════════════════════════════════════════
print("Plot 4: Source importance...")

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
fig.suptitle("Data Source Importance for Rug Detection", fontsize=15, fontweight="bold", y=1.02)

# Left: Model importance (from audit_and_train results)
model_imp = {"Helius": 77.1, "GoPlus": 22.9, "GeckoTerminal": 0.0}
src_names = list(model_imp.keys())
src_vals = list(model_imp.values())
src_colors = [COLORS[s] for s in src_names]

wedges, texts, autotexts = ax1.pie(
    [max(v, 0.5) for v in src_vals],  # min slice for visibility
    labels=src_names, colors=src_colors,
    autopct=lambda p: f"{p*sum(src_vals)/100:.1f}%",
    startangle=90, pctdistance=0.75,
    wedgeprops={"edgecolor": "#30363d", "linewidth": 2}
)
for t in texts:
    t.set_fontsize(11)
    t.set_fontweight("bold")
for t in autotexts:
    t.set_fontsize(10)
    t.set_color("#0d1117")
    t.set_fontweight("bold")
ax1.set_title("XGBoost Feature Importance\n(by source)", fontsize=12, pad=10)

# Right: Avg correlation by source
source_stats = corr_df.groupby("source").agg(
    avg_corr=("abs_corr", "mean"),
    n_features=("feature", "count"),
    max_corr=("abs_corr", "max"),
).sort_values("avg_corr", ascending=True)

bars = ax2.barh(range(len(source_stats)), source_stats["avg_corr"],
                color=[COLORS.get(s, "#8b949e") for s in source_stats.index],
                edgecolor="#30363d", height=0.6)
ax2.set_yticks(range(len(source_stats)))
ax2.set_yticklabels([f"{s} ({int(row['n_features'])} feats)" for s, row in source_stats.iterrows()], fontsize=10)
ax2.set_xlabel("Average |correlation| with Rug Label")
ax2.set_title("Avg Correlation Strength\n(by source)", fontsize=12, pad=10)
ax2.grid(axis="x", alpha=0.3)

for i, (val, mx) in enumerate(zip(source_stats["avg_corr"], source_stats["max_corr"])):
    ax2.text(val + 0.01, i, f"avg={val:.3f}, max={mx:.3f}", va="center", fontsize=9)

fig.tight_layout()
fig.savefig(f"{OUT}/source_importance_combined.png")
plt.close()
print(f"  → {OUT}/source_importance_combined.png")

# ═══════════════════════════════════════════════════════════════
# PLOT 5: Metadata URI Domain — Rug Rate by Hosting Service
# ═══════════════════════════════════════════════════════════════
print("Plot 5: Metadata URI domain rug rates...")

domain_data = labeled.copy()
domain_data["domain"] = domain_data["JSON_URI_DOMAIN"].fillna("(no URI)")

ct = domain_data.groupby("domain").agg(
    total=("IS_RUG", "count"),
    rugs=("IS_RUG", "sum")
).reset_index()
ct["rug_rate"] = ct["rugs"] / ct["total"] * 100
ct = ct[ct["total"] >= 50].sort_values("rug_rate", ascending=True)

fig, ax = plt.subplots(figsize=(12, 7))
colors = []
for rate in ct["rug_rate"]:
    if rate > 80:
        colors.append(RUG_COLOR)
    elif rate > 50:
        colors.append("#f0883e")
    elif rate > 30:
        colors.append("#d29922")
    else:
        colors.append(LEGIT_COLOR)

bars = ax.barh(range(len(ct)), ct["rug_rate"], color=colors, edgecolor="#30363d", height=0.65)
ax.set_yticks(range(len(ct)))
ax.set_yticklabels([f"{d}  (n={t:,})" for d, t in zip(ct["domain"], ct["total"])], fontsize=10)
ax.set_xlabel("Rug Rate (%)")
ax.set_title("Rug Rate by Metadata URI Domain\n(where token metadata is hosted)", fontsize=14, fontweight="bold", pad=15)
ax.axvline(50, color="#484f58", linestyle="--", alpha=0.5)
ax.grid(axis="x", alpha=0.3)

for i, (rate, total) in enumerate(zip(ct["rug_rate"], ct["total"])):
    ax.text(rate + 1, i, f"{rate:.1f}%", va="center", fontsize=10, fontweight="bold")

# Annotation
ax.text(0.98, 0.02, "🔴 Pinata & Irys = pump.fun rug factories\n🟢 No URI = older legit tokens",
        transform=ax.transAxes, ha="right", va="bottom", fontsize=10,
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#161b22", edgecolor="#30363d", alpha=0.9))

fig.savefig(f"{OUT}/rug_rate_by_uri_domain.png")
plt.close()
print(f"  → {OUT}/rug_rate_by_uri_domain.png")

# ═══════════════════════════════════════════════════════════════
# PLOT 6: Token Standard Rug Rate
# ═══════════════════════════════════════════════════════════════
print("Plot 6: Token standard breakdown...")

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
fig.suptitle("Token Standard & Rug Detection", fontsize=15, fontweight="bold", y=1.02)

# Token standard rug rate
std_data = labeled.copy()
std_data["standard"] = std_data["TOKEN_STANDARD"].fillna("(pre-metaplex / null)")
ct2 = std_data.groupby("standard").agg(total=("IS_RUG", "count"), rugs=("IS_RUG", "sum")).reset_index()
ct2["rug_rate"] = ct2["rugs"] / ct2["total"] * 100
ct2 = ct2.sort_values("rug_rate")

colors2 = [RUG_COLOR if r > 70 else "#f0883e" if r > 50 else LEGIT_COLOR for r in ct2["rug_rate"]]
ax1.barh(range(len(ct2)), ct2["rug_rate"], color=colors2, edgecolor="#30363d", height=0.5)
ax1.set_yticks(range(len(ct2)))
ax1.set_yticklabels([f"{s}\n(n={t:,})" for s, t in zip(ct2["standard"], ct2["total"])], fontsize=10)
ax1.set_xlabel("Rug Rate (%)")
ax1.set_title("Rug Rate by Token Standard", fontsize=12)
for i, rate in enumerate(ct2["rug_rate"]):
    ax1.text(rate + 1, i, f"{rate:.1f}%", va="center", fontsize=10, fontweight="bold")
ax1.grid(axis="x", alpha=0.3)

# Fill rate heatmap — key features
key_feats = ["TOKEN_PRICE_USD", "HAS_JSON_URI", "HAS_METADATA", "MINT_AUTHORITY_ACTIVE",
             "HAS_IMAGE", "IS_MUTABLE", "TOKEN_SUPPLY", "TOKEN_DECIMALS",
             "gp_lp_count", "gp_top3_holder_pct", "gp_total_tvl",
             "gt_pool_count", "gt_base_price_usd", "gt_reserve_usd"]
fill_data = []
for feat in key_feats:
    if feat not in labeled.columns:
        continue
    rug_fill = labeled.loc[labeled["IS_RUG"] == 1, feat].notna().mean() * 100
    legit_fill = labeled.loc[labeled["IS_RUG"] == 0, feat].notna().mean() * 100
    src = "GoPlus" if feat.startswith("gp_") else "GeckoTerminal" if feat.startswith("gt_") else "Helius"
    fill_data.append({"feature": feat, "Rug": rug_fill, "Legit": legit_fill, "source": src})

fill_df = pd.DataFrame(fill_data)
x2 = np.arange(len(fill_df))
w2 = 0.35
ax2.barh(x2 - w2/2, fill_df["Rug"], w2, label="Rug tokens", color=RUG_COLOR, alpha=0.8, edgecolor="#30363d")
ax2.barh(x2 + w2/2, fill_df["Legit"], w2, label="Legit tokens", color=LEGIT_COLOR, alpha=0.8, edgecolor="#30363d")
ax2.set_yticks(x2)
ax2.set_yticklabels(fill_df["feature"], fontsize=9)
ax2.set_xlabel("Fill Rate (%)")
ax2.set_title("Feature Fill Rate: Rug vs Legit", fontsize=12)
ax2.legend(fontsize=9)
ax2.grid(axis="x", alpha=0.3)
ax2.set_xlim(0, 110)

fig.tight_layout()
fig.savefig(f"{OUT}/token_standard_and_fill_rates.png")
plt.close()
print(f"  → {OUT}/token_standard_and_fill_rates.png")

# ═══════════════════════════════════════════════════════════════
# PLOT 7: GoPlus Feature Deep Dive (Box plots)
# ═══════════════════════════════════════════════════════════════
print("Plot 7: GoPlus feature deep dive...")

gp_feats = ["gp_lp_count", "gp_top3_holder_pct", "gp_total_tvl"]
gp_available = [f for f in gp_feats if f in labeled.columns and labeled[f].notna().sum() > 20]

if gp_available:
    fig, axes = plt.subplots(1, len(gp_available), figsize=(6 * len(gp_available), 6))
    if len(gp_available) == 1:
        axes = [axes]
    fig.suptitle("GoPlus Security Features — Rug vs Legit", fontsize=15, fontweight="bold", y=1.02)

    for i, feat in enumerate(gp_available):
        ax = axes[i]
        rug_d = labeled.loc[labeled["IS_RUG"] == 1, feat].dropna()
        legit_d = labeled.loc[labeled["IS_RUG"] == 0, feat].dropna()

        # Use violin + strip for small data
        plot_data = []
        for v in rug_d:
            plot_data.append({"value": v, "class": "Rug"})
        for v in legit_d:
            plot_data.append({"value": v, "class": "Legit"})
        pdf = pd.DataFrame(plot_data)

        if feat == "gp_total_tvl":
            pdf["value"] = np.log10(pdf["value"].clip(lower=0.01))
            ylabel = f"log₁₀({feat})"
        else:
            ylabel = feat

        parts = ax.violinplot(
            [pdf[pdf["class"] == "Rug"]["value"].values, pdf[pdf["class"] == "Legit"]["value"].values],
            positions=[0, 1], showmeans=True, showmedians=True
        )
        for pc, color in zip(parts["bodies"], [RUG_COLOR, LEGIT_COLOR]):
            pc.set_facecolor(color)
            pc.set_alpha(0.6)
        for key in ["cmeans", "cmedians", "cbars", "cmins", "cmaxes"]:
            if key in parts:
                parts[key].set_color("#c9d1d9")

        # Overlay actual points
        jitter_rug = np.random.normal(0, 0.04, len(rug_d))
        jitter_legit = np.random.normal(1, 0.04, len(legit_d))
        rug_vals = np.log10(rug_d.clip(lower=0.01)) if feat == "gp_total_tvl" else rug_d
        legit_vals = np.log10(legit_d.clip(lower=0.01)) if feat == "gp_total_tvl" else legit_d
        ax.scatter(jitter_rug, rug_vals, s=20, alpha=0.7, color=RUG_COLOR, edgecolors="#30363d", linewidths=0.5)
        ax.scatter(jitter_legit, legit_vals, s=20, alpha=0.7, color=LEGIT_COLOR, edgecolors="#30363d", linewidths=0.5)

        ax.set_xticks([0, 1])
        ax.set_xticklabels([f"Rug\n(n={len(rug_d)})", f"Legit\n(n={len(legit_d)})"], fontsize=11)
        ax.set_ylabel(ylabel)
        ax.set_title(feat, fontsize=12, fontweight="bold", color=COLORS["GoPlus"])
        ax.grid(axis="y", alpha=0.3)

        # Stats annotation
        r = labeled[[feat, "IS_RUG"]].dropna()[feat].corr(labeled[[feat, "IS_RUG"]].dropna()["IS_RUG"])
        ax.text(0.5, 0.02, f"r = {r:+.3f}", transform=ax.transAxes, ha="center",
                fontsize=10, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.3", facecolor=COLORS["GoPlus"], alpha=0.3, edgecolor=COLORS["GoPlus"]))

    fig.tight_layout()
    fig.savefig(f"{OUT}/goplus_features_violin.png")
    plt.close()
    print(f"  → {OUT}/goplus_features_violin.png")

# ═══════════════════════════════════════════════════════════════
# PLOT 8: Model Results Summary Card
# ═══════════════════════════════════════════════════════════════
print("Plot 8: Model results card...")

fig = plt.figure(figsize=(14, 8))
gs = GridSpec(2, 3, figure=fig, hspace=0.4, wspace=0.3)

# Title
fig.suptitle("DeFi Sentinel — AI Model Results", fontsize=18, fontweight="bold", y=0.98)

# Top-left: Main metrics
ax1 = fig.add_subplot(gs[0, 0])
metrics = {"AUC-ROC": 0.9736, "AUC-PR": 0.9689, "Precision": 0.955, "Recall": 0.774, "MCC": 0.77}
y_pos = np.arange(len(metrics))
vals = list(metrics.values())
bars = ax1.barh(y_pos, vals, color=[ACCENT] * len(vals), edgecolor="#30363d", height=0.5, alpha=0.9)
ax1.set_yticks(y_pos)
ax1.set_yticklabels(list(metrics.keys()), fontsize=11, fontweight="bold")
ax1.set_xlim(0, 1.15)
ax1.set_title("Model Metrics", fontsize=13, fontweight="bold")
for i, v in enumerate(vals):
    ax1.text(v + 0.02, i, f"{v:.4f}" if v < 1 else f"{v:.2f}",
             va="center", fontsize=10, fontweight="bold", color=LEGIT_COLOR if v > 0.9 else "#d29922")
ax1.grid(axis="x", alpha=0.3)
ax1.axvline(0.9, color=LEGIT_COLOR, linestyle="--", alpha=0.3)

# Top-middle: Feature importance (top 10)
ax2 = fig.add_subplot(gs[0, 1:])
fi = [
    ("TOKEN_PRICE_USD", 37.0, "Helius"),
    ("HAS_JSON_URI", 18.9, "Helius"),
    ("gp_lp_count", 16.8, "GoPlus"),
    ("HAS_METADATA", 5.0, "Helius"),
    ("MINT_AUTHORITY_ACTIVE", 4.1, "Helius"),
    ("TOKEN_SUPPLY", 3.8, "Helius"),
    ("gp_top3_holder_pct", 3.2, "GoPlus"),
    ("IS_MUTABLE", 2.5, "Helius"),
    ("TOKEN_DECIMALS", 2.3, "Helius"),
    ("HAS_IMAGE", 1.8, "Helius"),
]
fi_names = [f[0] for f in fi][::-1]
fi_vals = [f[1] for f in fi][::-1]
fi_colors = [COLORS[f[2]] for f in fi][::-1]

ax2.barh(range(10), fi_vals, color=fi_colors, edgecolor="#30363d", height=0.6)
ax2.set_yticks(range(10))
ax2.set_yticklabels(fi_names, fontsize=10)
ax2.set_xlabel("Importance (%)")
ax2.set_title("Top 10 Features (XGBoost Gain)", fontsize=13, fontweight="bold")
ax2.grid(axis="x", alpha=0.3)
for i, v in enumerate(fi_vals):
    ax2.text(v + 0.3, i, f"{v:.1f}%", va="center", fontsize=9, fontweight="bold")

patches = [mpatches.Patch(color=COLORS["Helius"], label="Helius (77.1%)"),
           mpatches.Patch(color=COLORS["GoPlus"], label="GoPlus (22.9%)")]
ax2.legend(handles=patches, loc="lower right", fontsize=9, framealpha=0.8)

# Bottom-left: Training config
ax3 = fig.add_subplot(gs[1, 0])
ax3.axis("off")
config_text = (
    "Training Configuration\n"
    "─────────────────────\n"
    "Algorithm:  XGBoost\n"
    "Trees:      300\n"
    "Max Depth:  6\n"
    "Split:      Temporal\n"
    "  Train:    <2024 (6,365)\n"
    "  Test:     2024 (23,238)\n"
    "Features:   36 live-equiv\n"
    "Labels:     Verified only\n"
    "  Rug:      15,369\n"
    "  Legit:    19,170"
)
ax3.text(0.1, 0.95, config_text, transform=ax3.transAxes, fontsize=10,
         fontfamily="monospace", va="top",
         bbox=dict(boxstyle="round,pad=0.5", facecolor="#0d1117", edgecolor="#30363d"))

# Bottom-middle: Verdict
ax4 = fig.add_subplot(gs[1, 1])
ax4.axis("off")
verdict_text = "🟢 EXCELLENT"
ax4.text(0.5, 0.6, verdict_text, transform=ax4.transAxes,
         fontsize=28, fontweight="bold", ha="center", va="center", color=LEGIT_COLOR)
ax4.text(0.5, 0.35, "AUC-ROC = 0.9736", transform=ax4.transAxes,
         fontsize=16, ha="center", va="center", color="#c9d1d9")
ax4.text(0.5, 0.15, "95.5% precision · 77.4% recall\n\"When we say rug, we're right 19/20 times\"",
         transform=ax4.transAxes, fontsize=10, ha="center", va="center", color="#8b949e", style="italic")

# Bottom-right: What's needed for 90%+ recall
ax5 = fig.add_subplot(gs[1, 2])
ax5.axis("off")
next_text = (
    "Path to 90%+ Recall\n"
    "────────────────────\n"
    "🔲 Enrich RugCheck 5K    +5-8%\n"
    "🔲 Enrich GoPlus 5K     +3-5%\n"
    "🔲 Creator Wallet feats  +3-5%\n"
    "🔲 Jupiter listing       +2-3%\n"
    "🔲 Derived features      +1-2%\n"
    "────────────────────\n"
    "Current: 77.4% recall\n"
    "Target:  90%+ recall"
)
ax5.text(0.1, 0.95, next_text, transform=ax5.transAxes, fontsize=10,
         fontfamily="monospace", va="top",
         bbox=dict(boxstyle="round,pad=0.5", facecolor="#0d1117", edgecolor="#30363d"))

fig.savefig(f"{OUT}/model_results_summary.png")
plt.close()
print(f"  → {OUT}/model_results_summary.png")

# ═══════════════════════════════════════════════════════════════
# PLOT 9: Correlation Heatmap (Top 15 features)
# ═══════════════════════════════════════════════════════════════
print("Plot 9: Correlation heatmap...")

top15 = corr_df.head(15)["feature"].tolist()
# Only include features with enough data
heatmap_feats = [f for f in top15 if labeled[f].notna().sum() > 500]
if len(heatmap_feats) > 3:
    hm_data = labeled[heatmap_feats + ["IS_RUG"]].dropna(thresh=2)
    corr_matrix = hm_data.corr()

    fig, ax = plt.subplots(figsize=(14, 11))
    mask = np.triu(np.ones_like(corr_matrix, dtype=bool), k=1)
    sns.heatmap(corr_matrix, mask=mask, annot=True, fmt=".2f", cmap="RdBu_r",
                center=0, vmin=-1, vmax=1, ax=ax,
                square=True, linewidths=0.5, linecolor="#30363d",
                cbar_kws={"shrink": 0.8},
                annot_kws={"size": 9})
    ax.set_title("Feature Correlation Heatmap (Top Predictors + IS_RUG)",
                 fontsize=14, fontweight="bold", pad=15)
    ax.tick_params(labelsize=10)

    fig.savefig(f"{OUT}/feature_correlation_heatmap.png")
    plt.close()
    print(f"  → {OUT}/feature_correlation_heatmap.png")

# ═══════════════════════════════════════════════════════════════
# PLOT 10: Missing Features Roadmap
# ═══════════════════════════════════════════════════════════════
print("Plot 10: Missing features roadmap...")

fig, ax = plt.subplots(figsize=(14, 8))
ax.set_xlim(0, 10)
ax.set_ylim(0, 10)
ax.axis("off")
ax.set_title("82-Feature Spec — Gap Analysis & Enrichment Roadmap",
             fontsize=16, fontweight="bold", pad=20)

# Draw boxes for each source
boxes = [
    # (x, y, width, height, source, have, total, missing_list, priority)
    (0.3, 6.5, 2.8, 3.0, "Helius", 14, 21,
     ["update_authority", "creation_timestamp", "metadata_uri_reachable",
      "has_description", "has_website", "has_twitter", "has_telegram"], "🟡 Medium"),
    (3.5, 6.5, 2.8, 3.0, "Creator\nWallet", 0, 6,
     ["sol_balance", "wallet_age", "token_count",
      "tx_count", "prev_rugged", "nft_count"], "🔴 Critical"),
    (6.8, 6.5, 2.8, 3.0, "RugCheck", 8, 18,
     ["mutable_metadata", "lp_locked", "lp_lock_pct",
      "lp_burned", "copycat_token", "num_markets", "...+4"], "🟠 High"),
    (0.3, 2.5, 2.8, 3.0, "Gecko\nTerminal", 16, 25,
     ["volume_5m", "price_change_6h", "tx_5m_buys",
      "tx_5m_sells", "tx_1h_buys", "tx_1h_sells", "...+3"], "🟡 Medium"),
    (3.5, 2.5, 2.8, 3.0, "Jupiter", 0, 5,
     ["listed", "strict_list", "daily_volume",
      "price_usd", "tags"], "🟠 High"),
    (6.8, 2.5, 2.8, 3.0, "Derived", 0, 7,
     ["liq_to_fdv_ratio", "sell_pressure", "metadata_complete",
      "authority_risk", "wallet_fresh", "consensus_risk", "price_liq_div"], "🟡 Free"),
]

for (x, y, w, h, name, have, total, missing, priority) in boxes:
    pct = have / total * 100
    # Box color based on coverage
    if pct >= 60:
        box_color = LEGIT_COLOR
    elif pct > 0:
        box_color = "#d29922"
    else:
        box_color = RUG_COLOR

    rect = mpatches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.1",
                                    facecolor=box_color, alpha=0.15, edgecolor=box_color, linewidth=2)
    ax.add_patch(rect)

    # Title
    ax.text(x + w/2, y + h - 0.3, name, ha="center", va="top",
            fontsize=12, fontweight="bold", color=box_color)
    # Coverage
    ax.text(x + w/2, y + h - 0.7, f"{have}/{total} ({pct:.0f}%)", ha="center", va="top",
            fontsize=10, color="#c9d1d9")
    # Priority
    ax.text(x + w/2, y + h - 1.0, priority, ha="center", va="top", fontsize=9)

    # Missing items
    for j, item in enumerate(missing[:6]):
        ax.text(x + 0.15, y + h - 1.4 - j * 0.22, f"• {item}", fontsize=7.5, color="#8b949e")

# Grand total
ax.text(5, 0.8, f"COVERAGE: 38/82 features (46%) + 47 bonus columns = 85 total features available",
        ha="center", fontsize=12, fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.5", facecolor=ACCENT, alpha=0.2, edgecolor=ACCENT))
ax.text(5, 0.2, "GoPlus (15 bonus features) not in spec but among our strongest predictors — recommend adding to spec",
        ha="center", fontsize=9, style="italic", color="#8b949e")

fig.savefig(f"{OUT}/feature_gap_roadmap.png")
plt.close()
print(f"  → {OUT}/feature_gap_roadmap.png")

# ═══════════════════════════════════════════════════════════════
# DONE
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*60}")
print(f"  ✅ Generated 10 visualizations in {OUT}/")
print(f"{'='*60}")
print(f"""
  1. feature_coverage_map.png          — 82-feature spec bar chart
  2. feature_correlations_top20.png    — top 20 features by |correlation|
  3. feature_distributions_top6.png    — rug vs legit histograms
  4. source_importance_combined.png    — pie chart + bar chart by source
  5. rug_rate_by_uri_domain.png        — metadata domain rug rates
  6. token_standard_and_fill_rates.png — token standard + fill rates
  7. goplus_features_violin.png        — GoPlus violin plots
  8. model_results_summary.png         — full model results card
  9. feature_correlation_heatmap.png   — top features correlation matrix
  10. feature_gap_roadmap.png          — missing features roadmap
""")
