#!/usr/bin/env python3
"""
SINGLE COMPREHENSIVE MODEL DASHBOARD — everything in one PNG.
Layout (4 rows × 3 cols + header):
  [HEADER: title + key metrics banner]
  [ROC curve] [PR curve] [Confusion matrix]
  [Feature importance top 15] [Score distribution] [Calibration]
  [Learning curve (rounds)] [Threshold analysis] [Temporal perf]
  [FOOTER: overfitting verdict + dataset info]
"""
import pandas as pd
import numpy as np
import json, os, warnings
warnings.filterwarnings('ignore')

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from matplotlib.patches import FancyBboxPatch, Patch
import matplotlib.patheffects as pe

# === STYLE ===
plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.size': 9,
    'axes.titlesize': 11,
    'axes.labelsize': 9,
})
BG      = '#0d1117'
CARD    = '#161b22'
ACCENT  = '#58a6ff'
GREEN   = '#3fb950'
RED     = '#f85149'
ORANGE  = '#d29922'
PURPLE  = '#bc8cff'
CYAN    = '#39d353'
GRAY    = '#8b949e'
WHITE   = '#e6edf3'
BORDER  = '#30363d'

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, 'data', 'enriched')
FIGS = os.path.join(BASE, 'data', 'figures')
os.makedirs(FIGS, exist_ok=True)

# ── Load & prepare ──────────────────────────────────────────────────
print("Loading data...")
df = pd.read_csv(os.path.join(DATA, 'enriched_v2.csv'), low_memory=False)
labels = pd.read_csv(os.path.join(DATA, 'verified_labels.csv'),
                      usecols=['MINT', 'LIQUIDITY_POOL_ADDRESS', 'RUG_LABEL'])
merged = df.merge(labels, on=['MINT', 'LIQUIDITY_POOL_ADDRESS'], how='left', suffixes=('', '_lab'))
rug = merged['RUG_LABEL'].isin(['VERIFIED_RUG', 'LIKELY_RUG'])
legit = merged['RUG_LABEL'] == 'LIKELY_LEGIT'
labeled = merged[rug | legit].copy()
labeled['IS_RUG'] = rug[labeled.index].astype(int)

POST_OUTCOME = {
    'TOKEN_PRICE_USD', 'TOTAL_REMOVED_LIQUIDITY', 'REMOVED_RATIO',
    'ADD_TO_REMOVE_RATIO', 'LIFESPAN_H', 'NUM_LIQUIDITY_REMOVES',
    'LAST_POOL_ACTIVITY_TIMESTAMP', 'LAST_SWAP_TIMESTAMP',
    'INACTIVITY_STATUS', 'NUM_SWAPS', 'TOTAL_SWAP_VOLUME',
    'derived_has_price', 'derived_pool_active_hours', 'derived_events_per_hour',
    'derived_drain_speed_pct_per_hour', 'derived_single_drain_flag',
    'derived_liquidity_depth_ratio', 'derived_avg_remove_size',
    'derived_remove_add_size_ratio'
}
IDS = {
    'MINT', 'LIQUIDITY_POOL_ADDRESS', 'OWNER', 'SOURCE',
    'POOL_OPEN_TIMESTAMP', 'POOL_OPEN_DATE', 'TOKEN_NAME', 'TOKEN_SYMBOL',
    'URI', 'URI_HASH', 'METADATA_URI', 'RAYDIUM_POOL_ID',
    'gt_pool_name', 'gt_pool_dex', 'gt_pool_created',
    'FIRST_POOL_ACTIVITY_TIMESTAMP', 'FIRST', 'LAST', 'TOKEN_PROGRAM',
    'MINT_AUTHORITY', 'RUG_LABEL', 'IS_RUG', 'RUG_LABEL_lab'
}
LEAKY = {
    'feat_deployer_token_count', 'feat_deployer_rug_count',
    'feat_deployer_rug_rate', 'feat_deployer_median_liquidity',
    'feat_deployer_is_rug_factory', 'feat_deployer_is_repeat',
}

feature_cols = [c for c in labeled.columns
                if c not in POST_OUTCOME and c not in IDS and c not in LEAKY
                and labeled[c].dtype in ['float64','int64','float32','int32','int8','uint8']]
good_features = [c for c in feature_cols if labeled[c].notna().mean() > 0.20]

ts = pd.to_datetime(labeled['FIRST_POOL_ACTIVITY_TIMESTAMP'], errors='coerce')
cutoff = pd.Timestamp('2024-01-01')
train_mask = ts < cutoff
test_mask  = ts >= cutoff

X_train = labeled.loc[train_mask, good_features].fillna(-1)
y_train = labeled.loc[train_mask, 'IS_RUG']
X_test  = labeled.loc[test_mask, good_features].fillna(-1)
y_test  = labeled.loc[test_mask, 'IS_RUG']

print(f"Train {len(X_train):,} | Test {len(X_test):,} | Features {len(good_features)}")

# ── Train ────────────────────────────────────────────────────────────
from xgboost import XGBClassifier
from sklearn.metrics import (roc_auc_score, roc_curve, precision_recall_curve,
    average_precision_score, confusion_matrix, matthews_corrcoef,
    brier_score_loss, log_loss, f1_score, precision_score, recall_score,
    accuracy_score)
from sklearn.calibration import calibration_curve

print("Training...")
model = XGBClassifier(
    n_estimators=400, max_depth=6, learning_rate=0.08,
    subsample=0.8, colsample_bytree=0.8,
    scale_pos_weight=len(y_train[y_train==0])/max(len(y_train[y_train==1]),1),
    random_state=42, eval_metric='logloss', verbosity=0
)
model.fit(X_train, y_train,
          eval_set=[(X_train, y_train), (X_test, y_test)], verbose=False)

y_tr_p = model.predict_proba(X_train)[:,1]
y_te_p = model.predict_proba(X_test)[:,1]
y_tr_pred = (y_tr_p >= 0.5).astype(int)
y_te_pred = (y_te_p >= 0.5).astype(int)

# Metrics
m = {}
m['train_auc']  = roc_auc_score(y_train, y_tr_p)
m['test_auc']   = roc_auc_score(y_test, y_te_p)
m['train_mcc']  = matthews_corrcoef(y_train, y_tr_pred)
m['test_mcc']   = matthews_corrcoef(y_test, y_te_pred)
m['test_prec']  = precision_score(y_test, y_te_pred)
m['test_rec']   = recall_score(y_test, y_te_pred)
m['test_f1']    = f1_score(y_test, y_te_pred)
m['test_acc']   = accuracy_score(y_test, y_te_pred)
m['brier']      = brier_score_loss(y_test, y_te_p)
m['train_ll']   = log_loss(y_train, y_tr_p)
m['test_ll']    = log_loss(y_test, y_te_p)

print(f"Test AUC={m['test_auc']:.4f}  MCC={m['test_mcc']:.4f}  F1={m['test_f1']:.4f}")

# ── BUILD THE DASHBOARD ─────────────────────────────────────────────
print("Building dashboard...")
fig = plt.figure(figsize=(24, 30), facecolor=BG)

# Grid: 5 rows (header, 3 content rows, footer) × 3 cols
# heights: header thin, 3 content equal, footer thin
gs = GridSpec(5, 3, figure=fig,
              height_ratios=[0.22, 1, 1, 1, 0.35],
              hspace=0.28, wspace=0.25,
              left=0.05, right=0.95, top=0.97, bottom=0.02)

# ═══════════════════════════════════════════════════════════════
# HEADER ROW — title + key metrics
# ═══════════════════════════════════════════════════════════════
ax_header = fig.add_subplot(gs[0, :])
ax_header.set_facecolor(BG)
ax_header.axis('off')

# Title
ax_header.text(0.5, 0.82, 'DeFi Sentinel — Model v3 Diagnostics Dashboard',
               transform=ax_header.transAxes, fontsize=26, fontweight='bold',
               color=WHITE, ha='center', va='top',
               path_effects=[pe.withStroke(linewidth=3, foreground=BG)])

ax_header.text(0.5, 0.58, 'XGBoost · 400 trees · depth=6 · lr=0.08 · temporal split (train < 2024 → test ≥ 2024) · creation-time features only',
               transform=ax_header.transAxes, fontsize=12, color=GRAY, ha='center', va='top')

# Metric cards
metric_cards = [
    ('AUC-ROC',   f"{m['test_auc']:.4f}",  ACCENT),
    ('MCC',       f"{m['test_mcc']:.4f}",  PURPLE),
    ('Precision',  f"{m['test_prec']:.1%}", GREEN),
    ('Recall',     f"{m['test_rec']:.1%}",  ORANGE),
    ('F1 Score',   f"{m['test_f1']:.4f}",  CYAN),
    ('Accuracy',   f"{m['test_acc']:.1%}",  WHITE),
    ('Brier',      f"{m['brier']:.4f}",    ACCENT),
]

n_cards = len(metric_cards)
card_w = 0.11
gap = (0.9 - n_cards * card_w) / (n_cards + 1)
for i, (label, value, color) in enumerate(metric_cards):
    cx = 0.05 + gap + i * (card_w + gap) + card_w / 2
    # Card background
    rect = FancyBboxPatch((cx - card_w/2, 0.0), card_w, 0.42,
                           boxstyle="round,pad=0.01", facecolor=CARD,
                           edgecolor=color, linewidth=1.5,
                           transform=ax_header.transAxes)
    ax_header.add_patch(rect)
    ax_header.text(cx, 0.32, value, transform=ax_header.transAxes,
                   fontsize=16, fontweight='bold', color=color, ha='center', va='center')
    ax_header.text(cx, 0.10, label, transform=ax_header.transAxes,
                   fontsize=10, color=GRAY, ha='center', va='center')

# ═══════════════════════════════════════════════════════════════
# ROW 1, COL 0 — ROC Curve
# ═══════════════════════════════════════════════════════════════
ax = fig.add_subplot(gs[1, 0])
ax.set_facecolor(CARD)

fpr_te, tpr_te, _ = roc_curve(y_test, y_te_p)
fpr_tr, tpr_tr, _ = roc_curve(y_train, y_tr_p)
ax.plot(fpr_tr, tpr_tr, color=ORANGE, lw=1.8, alpha=0.6, label=f'Train AUC={m["train_auc"]:.4f}')
ax.plot(fpr_te, tpr_te, color=ACCENT, lw=2.2, label=f'Test AUC={m["test_auc"]:.4f}')
ax.fill_between(fpr_te, tpr_te, alpha=0.12, color=ACCENT)
ax.plot([0,1],[0,1],'--', color=GRAY, alpha=0.4)
ax.set_xlabel('False Positive Rate', color=WHITE)
ax.set_ylabel('True Positive Rate', color=WHITE)
ax.set_title('ROC Curve', color=WHITE, fontweight='bold', fontsize=13)
ax.legend(fontsize=9, loc='lower right')
ax.tick_params(colors=GRAY)
for spine in ax.spines.values(): spine.set_color(BORDER)

# Zoomed inset
axins = ax.inset_axes([0.38, 0.12, 0.55, 0.42])
axins.set_facecolor(CARD)
axins.plot(fpr_tr, tpr_tr, color=ORANGE, lw=1.2, alpha=0.6)
axins.plot(fpr_te, tpr_te, color=ACCENT, lw=1.8)
axins.set_xlim([0, 0.04]); axins.set_ylim([0.96, 1.0])
axins.tick_params(colors=GRAY, labelsize=7)
for s in axins.spines.values(): s.set_color(BORDER)

# ═══════════════════════════════════════════════════════════════
# ROW 1, COL 1 — Precision-Recall Curve
# ═══════════════════════════════════════════════════════════════
ax = fig.add_subplot(gs[1, 1])
ax.set_facecolor(CARD)

prec_te, rec_te, _ = precision_recall_curve(y_test, y_te_p)
prec_tr, rec_tr, _ = precision_recall_curve(y_train, y_tr_p)
ap_te = average_precision_score(y_test, y_te_p)
ap_tr = average_precision_score(y_train, y_tr_p)

ax.plot(rec_tr, prec_tr, color=ORANGE, lw=1.8, alpha=0.6, label=f'Train AP={ap_tr:.4f}')
ax.plot(rec_te, prec_te, color=GREEN, lw=2.2, label=f'Test AP={ap_te:.4f}')
ax.fill_between(rec_te, prec_te, alpha=0.12, color=GREEN)
ax.axhline(y=y_test.mean(), color=GRAY, ls='--', alpha=0.4, label=f'Baseline={y_test.mean():.2f}')
ax.set_xlabel('Recall', color=WHITE); ax.set_ylabel('Precision', color=WHITE)
ax.set_title('Precision-Recall Curve', color=WHITE, fontweight='bold', fontsize=13)
ax.legend(fontsize=9, loc='lower left')
ax.tick_params(colors=GRAY)
for spine in ax.spines.values(): spine.set_color(BORDER)

# ═══════════════════════════════════════════════════════════════
# ROW 1, COL 2 — Confusion Matrix (test)
# ═══════════════════════════════════════════════════════════════
ax = fig.add_subplot(gs[1, 2])
ax.set_facecolor(CARD)

cm = confusion_matrix(y_test, y_te_pred)
cm_pct = cm / cm.sum() * 100
im = ax.imshow(cm_pct, cmap='Blues', aspect='auto', vmin=0, vmax=55)

labels_cm = [['True Neg\n(Legit→Legit)', 'False Pos\n(Legit→Rug)'],
             ['False Neg\n(Rug→Legit)',   'True Pos\n(Rug→Rug)']]
for i in range(2):
    for j in range(2):
        clr = 'white' if cm_pct[i,j] > 25 else GRAY
        ax.text(j, i, f'{labels_cm[i][j]}\n{cm[i,j]:,}\n({cm_pct[i,j]:.1f}%)',
               ha='center', va='center', fontsize=10, color=clr, fontweight='bold')

ax.set_xticks([0,1]); ax.set_yticks([0,1])
ax.set_xticklabels(['Pred Legit','Pred Rug'], color=WHITE, fontsize=10)
ax.set_yticklabels(['Actual Legit','Actual Rug'], color=WHITE, fontsize=10)
ax.set_title(f'Confusion Matrix (Test, n={len(y_test):,})', color=WHITE, fontweight='bold', fontsize=13)
for spine in ax.spines.values(): spine.set_color(BORDER)

# ═══════════════════════════════════════════════════════════════
# ROW 2, COL 0 — Feature Importance (top 15)
# ═══════════════════════════════════════════════════════════════
ax = fig.add_subplot(gs[2, 0])
ax.set_facecolor(CARD)

imp = dict(zip(good_features, model.feature_importances_))
sorted_imp = sorted(imp.items(), key=lambda x: x[1])[-15:]
names = [f[0] for f in sorted_imp]
vals  = [f[1]*100 for f in sorted_imp]

# Shorten names for readability
short = []
for n in names:
    s = n.replace('feat_deployer_past_', 'depl_').replace('feat_', 'f_')
    s = s.replace('INITIAL_LIQUIDITY_SOL', 'INIT_LIQ_SOL')
    s = s.replace('derived_', 'd_').replace('TOKEN_TOTAL_SUPPLY', 'TOT_SUPPLY')
    short.append(s)

colors = [RED if 'depl' in s else (ACCENT if s.startswith('f_') else GRAY) for s in short]
bars = ax.barh(range(len(short)), vals, color=colors, height=0.7)
ax.set_yticks(range(len(short)))
ax.set_yticklabels(short, color=WHITE, fontsize=8.5)
ax.set_xlabel('Importance %', color=WHITE)
ax.set_title('Top 15 Features (Gain)', color=WHITE, fontweight='bold', fontsize=13)
ax.tick_params(colors=GRAY)
for spine in ax.spines.values(): spine.set_color(BORDER)

# Importance % labels
for bar, v in zip(bars, vals):
    if v > 0.3:
        ax.text(bar.get_width()+0.2, bar.get_y()+bar.get_height()/2,
               f'{v:.1f}%', va='center', color=WHITE, fontsize=8)

legend_el = [Patch(facecolor=RED, label='Deployer history'),
             Patch(facecolor=ACCENT, label='Engineered'),
             Patch(facecolor=GRAY, label='Original')]
ax.legend(handles=legend_el, fontsize=8, loc='lower right')

# ═══════════════════════════════════════════════════════════════
# ROW 2, COL 1 — Score Distribution
# ═══════════════════════════════════════════════════════════════
ax = fig.add_subplot(gs[2, 1])
ax.set_facecolor(CARD)

bins = np.linspace(0, 1, 60)
ax.hist(y_te_p[y_test==0], bins=bins, alpha=0.7, color=GREEN, density=True,
        label=f'Legit (n={int((y_test==0).sum()):,})')
ax.hist(y_te_p[y_test==1], bins=bins, alpha=0.7, color=RED, density=True,
        label=f'Rug (n={int((y_test==1).sum()):,})')
ax.axvline(x=0.5, color=WHITE, ls='--', lw=1.5, alpha=0.6, label='Threshold')
ax.set_xlabel('P(Rug)', color=WHITE); ax.set_ylabel('Density', color=WHITE)
ax.set_title('Score Distribution (Test)', color=WHITE, fontweight='bold', fontsize=13)
ax.legend(fontsize=9)
ax.tick_params(colors=GRAY)
for spine in ax.spines.values(): spine.set_color(BORDER)

# ═══════════════════════════════════════════════════════════════
# ROW 2, COL 2 — Calibration
# ═══════════════════════════════════════════════════════════════
ax = fig.add_subplot(gs[2, 2])
ax.set_facecolor(CARD)

prob_true, prob_pred = calibration_curve(y_test, y_te_p, n_bins=15, strategy='quantile')
ax.plot(prob_pred, prob_true, 'o-', color=ACCENT, lw=2, ms=6, label='Model')
ax.plot([0,1],[0,1],'--', color=GRAY, lw=1.5, label='Perfect')
ax.fill_between(prob_pred, prob_true, prob_pred, alpha=0.15, color=ACCENT)
ax.set_xlabel('Predicted P(Rug)', color=WHITE); ax.set_ylabel('Actual Fraction', color=WHITE)
ax.set_title(f'Calibration (Brier={m["brier"]:.4f})', color=WHITE, fontweight='bold', fontsize=13)
ax.legend(fontsize=9)
ax.set_xlim([-0.05,1.05]); ax.set_ylim([-0.05,1.05])
ax.tick_params(colors=GRAY)
for spine in ax.spines.values(): spine.set_color(BORDER)

# ═══════════════════════════════════════════════════════════════
# ROW 3, COL 0 — Learning Curve (boosting rounds)
# ═══════════════════════════════════════════════════════════════
ax = fig.add_subplot(gs[3, 0])
ax.set_facecolor(CARD)

res = model.evals_result()
tr_ll = res['validation_0']['logloss']
te_ll = res['validation_1']['logloss']
ax.plot(tr_ll, color=ORANGE, lw=1.8, label='Train')
ax.plot(te_ll, color=ACCENT, lw=1.8, label='Test')
gap = te_ll[-1] - tr_ll[-1]
ax.set_xlabel('Boosting Round', color=WHITE); ax.set_ylabel('Log Loss', color=WHITE)
ax.set_title('Learning Curve', color=WHITE, fontweight='bold', fontsize=13)
ax.legend(fontsize=9)
ax.tick_params(colors=GRAY)
for spine in ax.spines.values(): spine.set_color(BORDER)

# Gap annotation
verdict_color = GREEN if gap < 0.05 else RED
ax.annotate(f'Final gap={gap:.4f}\n{"✓ Healthy" if gap < 0.05 else "⚠ Overfit"}',
           xy=(380, te_ll[-1]), fontsize=9, color=verdict_color, fontweight='bold',
           xytext=(200, max(te_ll)*0.7),
           arrowprops=dict(arrowstyle='->', color=verdict_color, lw=1.5))

# ═══════════════════════════════════════════════════════════════
# ROW 3, COL 1 — Threshold Analysis
# ═══════════════════════════════════════════════════════════════
ax = fig.add_subplot(gs[3, 1])
ax.set_facecolor(CARD)

thresholds = np.arange(0.05, 0.96, 0.01)
precs_t, recs_t, f1s_t, mccs_t = [], [], [], []
for t in thresholds:
    pred = (y_te_p >= t).astype(int)
    tp = ((pred==1)&(y_test==1)).sum()
    fp = ((pred==1)&(y_test==0)).sum()
    fn = ((pred==0)&(y_test==1)).sum()
    p = tp/(tp+fp) if (tp+fp)>0 else 0
    r = tp/(tp+fn) if (tp+fn)>0 else 0
    f = 2*p*r/(p+r) if (p+r)>0 else 0
    precs_t.append(p); recs_t.append(r); f1s_t.append(f)
    mccs_t.append(matthews_corrcoef(y_test, pred))

ax.plot(thresholds, precs_t, color=ACCENT, lw=1.8, label='Precision')
ax.plot(thresholds, recs_t, color=GREEN, lw=1.8, label='Recall')
ax.plot(thresholds, f1s_t, color=PURPLE, lw=1.8, label='F1')
ax.plot(thresholds, mccs_t, color=ORANGE, lw=1.8, label='MCC')
ax.axvline(x=0.5, color=WHITE, ls='--', alpha=0.4)
best_f1_t = thresholds[np.argmax(f1s_t)]
ax.axvline(x=best_f1_t, color=PURPLE, ls=':', alpha=0.6)
ax.set_xlabel('Threshold', color=WHITE); ax.set_ylabel('Score', color=WHITE)
ax.set_title('Threshold Sweep', color=WHITE, fontweight='bold', fontsize=13)
ax.legend(fontsize=8, ncol=2, loc='lower left')
ax.tick_params(colors=GRAY)
for spine in ax.spines.values(): spine.set_color(BORDER)

# ═══════════════════════════════════════════════════════════════
# ROW 3, COL 2 — Temporal Performance
# ═══════════════════════════════════════════════════════════════
ax = fig.add_subplot(gs[3, 2])
ax.set_facecolor(CARD)

test_ts = pd.to_datetime(labeled.loc[test_mask, 'FIRST_POOL_ACTIVITY_TIMESTAMP'], errors='coerce')
tdf = pd.DataFrame({'ts': test_ts.values, 'y': y_test.values, 'p': y_te_p, 'pred': y_te_pred})
tdf['month'] = pd.to_datetime(tdf['ts']).dt.to_period('M')
tdf = tdf.dropna(subset=['month'])

monthly = tdf.groupby('month').apply(
    lambda g: pd.Series({
        'n': len(g),
        'auc': roc_auc_score(g['y'], g['p']) if g['y'].nunique()>1 else np.nan,
        'prec': precision_score(g['y'], g['pred'], zero_division=0),
        'rec': recall_score(g['y'], g['pred'], zero_division=0),
    })
).reset_index()

x = range(len(monthly))
ms = [str(p) for p in monthly['month']]
ax.plot(x, monthly['auc'], 'o-', color=ACCENT, lw=1.8, ms=5, label='AUC')
ax.plot(x, monthly['prec'], 's-', color=GREEN, lw=1.8, ms=5, label='Precision')
ax.plot(x, monthly['rec'], '^-', color=ORANGE, lw=1.8, ms=5, label='Recall')
ax.set_xticks(x); ax.set_xticklabels(ms, rotation=45, fontsize=7, color=GRAY)
ax.set_ylabel('Score', color=WHITE)
ax.set_title('Temporal Generalization (monthly)', color=WHITE, fontweight='bold', fontsize=13)
ax.legend(fontsize=8, loc='lower left')
ax.set_ylim([0.90, 1.01])
ax.tick_params(colors=GRAY)
for spine in ax.spines.values(): spine.set_color(BORDER)

# ═══════════════════════════════════════════════════════════════
# FOOTER — Overfitting verdict + dataset info
# ═══════════════════════════════════════════════════════════════
ax_foot = fig.add_subplot(gs[4, :])
ax_foot.set_facecolor(BG)
ax_foot.axis('off')

# Left block: overfitting check
checks = [
    (f"AUC gap:  {m['train_auc']-m['test_auc']:.4f}", m['train_auc']-m['test_auc'] < 0.01),
    (f"MCC gap:  {m['train_mcc']-m['test_mcc']:.4f}", m['train_mcc']-m['test_mcc'] < 0.05),
    (f"LogLoss gap: {m['test_ll']-m['train_ll']:.4f}", m['test_ll']-m['train_ll'] < 0.05),
    (f"Brier score: {m['brier']:.4f}", m['brier'] < 0.02),
]

ax_foot.text(0.02, 0.92, 'OVERFITTING CHECK', color=WHITE, fontsize=13,
            fontweight='bold', transform=ax_foot.transAxes, va='top')

for i, (txt, ok) in enumerate(checks):
    icon = '✅' if ok else '⚠️'
    color = GREEN if ok else RED
    ax_foot.text(0.02, 0.72 - i*0.20, f'{icon}  {txt}',
                color=color, fontsize=11, transform=ax_foot.transAxes, va='top',
                fontfamily='monospace')

# Center block: split info
ax_foot.text(0.35, 0.92, 'DATA SPLIT', color=WHITE, fontsize=13,
            fontweight='bold', transform=ax_foot.transAxes, va='top')
split_info = [
    f"Train: {len(X_train):,} samples  (< 2024)   rug rate: {y_train.mean():.1%}",
    f"Test:  {len(X_test):,} samples  (≥ 2024)   rug rate: {y_test.mean():.1%}",
    f"Split type: TEMPORAL (forward-looking, honest)",
    f"Features: {len(good_features)} creation-time only, no post-outcome",
]
for i, txt in enumerate(split_info):
    ax_foot.text(0.35, 0.72 - i*0.20, txt, color=GRAY, fontsize=10,
                transform=ax_foot.transAxes, va='top', fontfamily='monospace')

# Right block: model config
ax_foot.text(0.72, 0.92, 'MODEL CONFIG', color=WHITE, fontsize=13,
            fontweight='bold', transform=ax_foot.transAxes, va='top')
config_info = [
    "XGBoost v3 — 400 estimators, depth=6, lr=0.08",
    "subsample=0.8, colsample=0.8, scale_pos_weight=auto",
    f"Deployer features = {sum(v for k,v in imp.items() if 'deployer' in k)/sum(imp.values())*100:.0f}% of total importance",
    f"Engineered features = {sum(v for k,v in imp.items() if k.startswith('feat_'))/sum(imp.values())*100:.0f}% of total importance",
]
for i, txt in enumerate(config_info):
    ax_foot.text(0.72, 0.72 - i*0.20, txt, color=GRAY, fontsize=10,
                transform=ax_foot.transAxes, va='top', fontfamily='monospace')

# ── Save ──
out = os.path.join(FIGS, 'model_dashboard.png')
fig.savefig(out, dpi=150, facecolor=BG, bbox_inches='tight')
plt.close()
sz = os.path.getsize(out) // 1024
print(f"\n✅ Saved: {out} ({sz}KB)")
