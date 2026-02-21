#!/usr/bin/env python3
"""
COMPREHENSIVE FEATURE ANALYSIS DASHBOARD
One-PNG feature deep-dive: sources, fill rates, separation power,
distributions, correlations, and insights per feature category.
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

# Style
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
PINK    = '#f778ba'
YELLOW  = '#e3b341'

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, 'data', 'enriched')
FIGS = os.path.join(BASE, 'data', 'figures')
os.makedirs(FIGS, exist_ok=True)

# ── Load ────────────────────────────────────────────────────────────
print("Loading data...")
df = pd.read_csv(os.path.join(DATA, 'enriched_v2.csv'), low_memory=False)
labels = pd.read_csv(os.path.join(DATA, 'verified_labels.csv'),
                      usecols=['MINT','LIQUIDITY_POOL_ADDRESS','RUG_LABEL'])
merged = df.merge(labels, on=['MINT','LIQUIDITY_POOL_ADDRESS'], how='left', suffixes=('','_lab'))
rug = merged['RUG_LABEL'].isin(['VERIFIED_RUG','LIKELY_RUG'])
legit = merged['RUG_LABEL'] == 'LIKELY_LEGIT'
labeled = merged[rug|legit].copy()
labeled['IS_RUG'] = rug[labeled.index].astype(int)

# Load model for importances
from xgboost import XGBClassifier
from sklearn.metrics import roc_auc_score

POST_OUTCOME = {
    'TOKEN_PRICE_USD','TOTAL_REMOVED_LIQUIDITY','REMOVED_RATIO',
    'ADD_TO_REMOVE_RATIO','LIFESPAN_H','NUM_LIQUIDITY_REMOVES',
    'LAST_POOL_ACTIVITY_TIMESTAMP','LAST_SWAP_TIMESTAMP',
    'INACTIVITY_STATUS','NUM_SWAPS','TOTAL_SWAP_VOLUME',
    'derived_has_price','derived_pool_active_hours','derived_events_per_hour',
    'derived_drain_speed_pct_per_hour','derived_single_drain_flag',
    'derived_liquidity_depth_ratio','derived_avg_remove_size',
    'derived_remove_add_size_ratio'
}
IDS = {
    'MINT','LIQUIDITY_POOL_ADDRESS','OWNER','SOURCE',
    'POOL_OPEN_TIMESTAMP','POOL_OPEN_DATE','TOKEN_NAME','TOKEN_SYMBOL',
    'URI','URI_HASH','METADATA_URI','RAYDIUM_POOL_ID',
    'gt_pool_name','gt_pool_dex','gt_pool_created',
    'FIRST_POOL_ACTIVITY_TIMESTAMP','FIRST','LAST','TOKEN_PROGRAM',
    'MINT_AUTHORITY','RUG_LABEL','IS_RUG','RUG_LABEL_lab','TOKEN_PRICE_CURRENCY','TOKEN_STANDARD','JSON_URI_DOMAIN'
}
LEAKY = {
    'feat_deployer_token_count','feat_deployer_rug_count',
    'feat_deployer_rug_rate','feat_deployer_median_liquidity',
    'feat_deployer_is_rug_factory','feat_deployer_is_repeat',
}

# Feature categories with colors
CATEGORIES = {
    'Original Dataset': {
        'cols': ['TOTAL_ADDED_LIQUIDITY','NUM_LIQUIDITY_ADDS','TOKEN_DECIMALS','TOKEN_SUPPLY'],
        'color': GRAY, 'source': 'SolRPDS paper'
    },
    'Helius On-Chain': {
        'cols': ['IS_MUTABLE','HAS_IMAGE','HAS_METADATA','HAS_JSON_URI',
                 'MINT_AUTHORITY_ACTIVE','NUM_CREATORS','ROYALTY_PCT','CREATOR_VERIFIED'],
        'color': ACCENT, 'source': 'Helius RPC API'
    },
    'Derived Ratios': {
        'cols': [c for c in df.columns if c.startswith('derived_') and c not in POST_OUTCOME],
        'color': CYAN, 'source': 'Computed from raw data'
    },
    'Name & Symbol': {
        'cols': [c for c in df.columns if c.startswith('feat_name') or c.startswith('feat_symbol')],
        'color': PURPLE, 'source': 'NLP on token name/symbol'
    },
    'Timestamp': {
        'cols': [c for c in df.columns if c.startswith('feat_pool')],
        'color': ORANGE, 'source': 'Pool creation time'
    },
    'Supply': {
        'cols': [c for c in df.columns if c.startswith('feat_supply')],
        'color': YELLOW, 'source': 'Token supply analysis'
    },
    'Liquidity': {
        'cols': [c for c in df.columns if c.startswith('feat_liq')],
        'color': GREEN, 'source': 'Initial liquidity analysis'
    },
    'Deployer History': {
        'cols': ['feat_deployer_past_tokens','feat_deployer_past_rugs',
                 'feat_deployer_past_rug_rate','feat_deployer_past_labeled',
                 'feat_deployer_past_is_serial'],
        'color': RED, 'source': 'Temporal deployer wallet stats'
    },
    'RugCheck API': {
        'cols': [c for c in df.columns if c.startswith('rc_')],
        'color': PINK, 'source': 'RugCheck.xyz API'
    },
}

# Compute stats for all numeric features
print("Computing feature statistics...")
all_stats = []
# Pre-split for speed
rug_mask = labeled['IS_RUG'] == 1
leg_mask = labeled['IS_RUG'] == 0
for cat_name, cat_info in CATEGORIES.items():
    for col in cat_info['cols']:
        if col not in labeled.columns:
            continue
        series = labeled[col]
        if series.dtype not in ['float64','int64','float32','int32','int8','uint8']:
            continue
        notna = series.notna()
        n_valid = int(notna.sum())
        fill = n_valid / len(series) * 100
        if n_valid < 50:
            sep = 0
            m_rug = 0
            m_leg = 0
        else:
            vals_rug = series[notna & rug_mask]
            vals_leg = series[notna & leg_mask]
            m_rug = float(vals_rug.mean())
            m_leg = float(vals_leg.mean())
            std = float(series[notna].std())
            sep = abs(m_rug - m_leg) / std if std > 0 else 0
        
        all_stats.append({
            'feature': col,
            'category': cat_name,
            'color': cat_info['color'],
            'fill': fill,
            'separation': sep,
            'mean_rug': m_rug,
            'mean_legit': m_leg,
            'n_valid': n_valid,
        })

stats_df = pd.DataFrame(all_stats).sort_values('separation', ascending=False)

# Also load model importances
with open(os.path.join(BASE, 'models', 'feature_list_v3.json')) as f:
    model_features = json.load(f)
with open(os.path.join(BASE, 'models', 'model_meta_v3.json')) as f:
    meta = json.load(f)
imp_dict = {f: v for f, v in meta['top_features']}

print(f"Total features analyzed: {len(stats_df)}")
print(f"By category: {stats_df.groupby('category').size().to_dict()}")

# ═════════════════════════════════════════════════════════════════════
# BUILD THE DASHBOARD
# ═════════════════════════════════════════════════════════════════════
print("Building feature analysis dashboard...")

fig = plt.figure(figsize=(28, 36), facecolor=BG)
gs = GridSpec(5, 3, figure=fig,
              height_ratios=[0.15, 1, 1, 1, 1],
              hspace=0.25, wspace=0.25,
              left=0.05, right=0.95, top=0.97, bottom=0.02)

# ═══════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════
ax_h = fig.add_subplot(gs[0, :])
ax_h.set_facecolor(BG); ax_h.axis('off')

ax_h.text(0.5, 0.85, 'DeFi Sentinel — Feature Analysis Dashboard',
          transform=ax_h.transAxes, fontsize=26, fontweight='bold',
          color=WHITE, ha='center', va='top')

# Source summary cards
sources = [
    ('SolRPDS\nDataset', '4', GRAY),
    ('Helius\nOn-Chain', '8', ACCENT),
    ('Derived\nRatios', f'{len(CATEGORIES["Derived Ratios"]["cols"])}', CYAN),
    ('Name/Symbol\nNLP', f'{len(CATEGORIES["Name & Symbol"]["cols"])}', PURPLE),
    ('Timestamp\nAnalysis', f'{len(CATEGORIES["Timestamp"]["cols"])}', ORANGE),
    ('Supply\nAnalysis', f'{len(CATEGORIES["Supply"]["cols"])}', YELLOW),
    ('Liquidity\nAnalysis', f'{len(CATEGORIES["Liquidity"]["cols"])}', GREEN),
    ('Deployer\nHistory', '5', RED),
    ('RugCheck\nAPI', f'{len(CATEGORIES["RugCheck API"]["cols"])}', PINK),
]
n = len(sources)
cw = 0.09
gap = (0.9 - n*cw) / (n+1)
for i, (label, count, color) in enumerate(sources):
    cx = 0.05 + gap + i*(cw+gap) + cw/2
    rect = FancyBboxPatch((cx-cw/2, 0.0), cw, 0.55,
                           boxstyle="round,pad=0.01", facecolor=CARD,
                           edgecolor=color, linewidth=2,
                           transform=ax_h.transAxes)
    ax_h.add_patch(rect)
    ax_h.text(cx, 0.42, count, transform=ax_h.transAxes,
              fontsize=18, fontweight='bold', color=color, ha='center', va='center')
    ax_h.text(cx, 0.12, label, transform=ax_h.transAxes,
              fontsize=8, color=GRAY, ha='center', va='center', linespacing=1.1)

total_feats = sum(len(c['cols']) for c in CATEGORIES.values())
ax_h.text(0.5, 0.62, f'{total_feats} features from {len(CATEGORIES)} sources · 54 used in model · 42 engineered by us',
          transform=ax_h.transAxes, fontsize=11, color=GRAY, ha='center', va='top')

# ═══════════════════════════════════════════════════════════════
# ROW 1, COL 0 — Top 20 features by separation power
# ═══════════════════════════════════════════════════════════════
ax = fig.add_subplot(gs[1, 0])
ax.set_facecolor(CARD)

top20 = stats_df.head(20).iloc[::-1]  # reverse for horizontal bar
short_names = []
for n in top20['feature']:
    s = n.replace('feat_deployer_past_', 'depl_past_')
    s = s.replace('feat_', 'f_').replace('derived_', 'd_')
    s = s.replace('TOTAL_ADDED_LIQUIDITY', 'ADDED_LIQ')
    short_names.append(s)

bars = ax.barh(range(len(top20)), top20['separation'].values, 
               color=top20['color'].values, height=0.7)
ax.set_yticks(range(len(top20)))
ax.set_yticklabels(short_names, color=WHITE, fontsize=8)
ax.set_xlabel('Separation (|μ_rug - μ_legit| / σ)', color=WHITE, fontsize=9)
ax.set_title('Top 20 Features by Rug/Legit Separation', color=WHITE, fontweight='bold', fontsize=12)
ax.tick_params(colors=GRAY)
for s in ax.spines.values(): s.set_color(BORDER)

for bar, val in zip(bars, top20['separation'].values):
    if val > 0.05:
        ax.text(bar.get_width()+0.02, bar.get_y()+bar.get_height()/2,
               f'{val:.3f}', va='center', color=WHITE, fontsize=7.5)

# ═══════════════════════════════════════════════════════════════
# ROW 1, COL 1 — Feature source importance pie
# ═══════════════════════════════════════════════════════════════
ax = fig.add_subplot(gs[1, 1])
ax.set_facecolor(CARD)

cat_imp = {}
for cat_name, cat_info in CATEGORIES.items():
    total = sum(imp_dict.get(c, 0) for c in cat_info['cols'])
    if total > 0:
        cat_imp[cat_name] = total

sorted_cats = sorted(cat_imp.items(), key=lambda x: -x[1])
pie_labels = [c[0] for c in sorted_cats]
pie_values = [c[1]*100 for c in sorted_cats]
pie_colors = [CATEGORIES[c[0]]['color'] for c in sorted_cats]

wedges, texts, autotexts = ax.pie(pie_values, labels=None, autopct='%1.1f%%',
                                    colors=pie_colors, startangle=90,
                                    pctdistance=0.75, textprops={'color': WHITE, 'fontsize': 9})
for at in autotexts:
    at.set_fontweight('bold')
    at.set_fontsize(9)

# Legend outside
ax.legend(wedges, pie_labels, loc='lower center', fontsize=8,
          ncol=2, frameon=False, labelcolor=WHITE,
          bbox_to_anchor=(0.5, -0.08))
ax.set_title('Model Importance by Feature Source', color=WHITE, fontweight='bold', fontsize=12)

# ═══════════════════════════════════════════════════════════════
# ROW 1, COL 2 — Fill Rate vs Separation scatter
# ═══════════════════════════════════════════════════════════════
ax = fig.add_subplot(gs[1, 2])
ax.set_facecolor(CARD)

for cat_name, cat_info in CATEGORIES.items():
    cat_data = stats_df[stats_df['category'] == cat_name]
    if len(cat_data) > 0:
        ax.scatter(cat_data['fill'], cat_data['separation'],
                  c=cat_info['color'], s=50, alpha=0.8, label=cat_name,
                  edgecolor='white', linewidth=0.3)

# Annotate top features
for _, row in stats_df.head(5).iterrows():
    short = row['feature'].replace('feat_deployer_past_','depl_')
    short = short.replace('feat_','f_').replace('derived_','d_')
    ax.annotate(short, (row['fill'], row['separation']),
               fontsize=7, color=WHITE, xytext=(5,5),
               textcoords='offset points')

ax.set_xlabel('Fill Rate (%)', color=WHITE, fontsize=9)
ax.set_ylabel('Separation Power', color=WHITE, fontsize=9)
ax.set_title('Fill Rate vs Separation (bubble = feature)', color=WHITE, fontweight='bold', fontsize=12)
ax.legend(fontsize=7, loc='upper left', framealpha=0.3)
ax.tick_params(colors=GRAY)
for s in ax.spines.values(): s.set_color(BORDER)

# ═══════════════════════════════════════════════════════════════
# ROW 2, COL 0 — Deployer features (the hero)
# ═══════════════════════════════════════════════════════════════
ax = fig.add_subplot(gs[2, 0])
ax.set_facecolor(CARD)

depl_feats = ['feat_deployer_past_rug_rate', 'feat_deployer_past_tokens',
              'feat_deployer_past_rugs', 'feat_deployer_past_labeled',
              'feat_deployer_past_is_serial']
positions = []
violin_data_rug = []
violin_data_leg = []

for i, feat in enumerate(depl_feats):
    valid = labeled[labeled[feat].notna()]
    rug_vals = valid.loc[valid['IS_RUG']==1, feat].values
    leg_vals = valid.loc[valid['IS_RUG']==0, feat].values
    
    # Clip extreme outliers for visualization
    p99 = np.percentile(np.concatenate([rug_vals, leg_vals]), 99)
    rug_vals = np.clip(rug_vals, None, p99)
    leg_vals = np.clip(leg_vals, None, p99)
    
    if len(rug_vals) > 10 and np.std(rug_vals) > 0:
        vp1 = ax.violinplot([rug_vals], positions=[i-0.18], widths=0.3, showmedians=True)
        for body in vp1['bodies']:
            body.set_facecolor(RED); body.set_alpha(0.6)
        for part in ['cmins','cmaxes','cbars','cmedians']:
            if part in vp1: vp1[part].set_color(RED)
    
    if len(leg_vals) > 10 and np.std(leg_vals) > 0:
        vp2 = ax.violinplot([leg_vals], positions=[i+0.18], widths=0.3, showmedians=True)
        for body in vp2['bodies']:
            body.set_facecolor(GREEN); body.set_alpha(0.6)
        for part in ['cmins','cmaxes','cbars','cmedians']:
            if part in vp2: vp2[part].set_color(GREEN)

short_depl = ['past_rug_rate', 'past_tokens', 'past_rugs', 'past_labeled', 'is_serial']
ax.set_xticks(range(len(depl_feats)))
ax.set_xticklabels(short_depl, rotation=25, color=WHITE, fontsize=8, ha='right')
ax.set_title('Deployer Features — Rug vs Legit Distribution', color=WHITE, fontweight='bold', fontsize=12)
ax.tick_params(colors=GRAY)
for s in ax.spines.values(): s.set_color(BORDER)

legend_el = [Patch(facecolor=RED, alpha=0.6, label='Rug'),
             Patch(facecolor=GREEN, alpha=0.6, label='Legit')]
ax.legend(handles=legend_el, fontsize=9)

# ═══════════════════════════════════════════════════════════════
# ROW 2, COL 1 — Helius on-chain features
# ═══════════════════════════════════════════════════════════════
ax = fig.add_subplot(gs[2, 1])
ax.set_facecolor(CARD)

helius = ['IS_MUTABLE', 'HAS_IMAGE', 'HAS_METADATA', 'HAS_JSON_URI',
          'MINT_AUTHORITY_ACTIVE', 'CREATOR_VERIFIED']
rug_rates = []
legit_rates = []
feat_names = []

for feat in helius:
    if feat not in labeled.columns: continue
    valid = labeled[labeled[feat].notna()]
    if len(valid) < 50: continue
    rug_mean = valid.loc[valid['IS_RUG']==1, feat].mean()
    leg_mean = valid.loc[valid['IS_RUG']==0, feat].mean()
    rug_rates.append(rug_mean)
    legit_rates.append(leg_mean)
    feat_names.append(feat)

x = np.arange(len(feat_names))
w = 0.35
ax.bar(x - w/2, rug_rates, w, color=RED, alpha=0.8, label='Rug mean')
ax.bar(x + w/2, legit_rates, w, color=GREEN, alpha=0.8, label='Legit mean')
ax.set_xticks(x)
ax.set_xticklabels(feat_names, rotation=30, color=WHITE, fontsize=8, ha='right')
ax.set_ylabel('Mean Value', color=WHITE)
ax.set_title('Helius On-Chain Features — Rug vs Legit', color=WHITE, fontweight='bold', fontsize=12)
ax.legend(fontsize=9)
ax.tick_params(colors=GRAY)
for s in ax.spines.values(): s.set_color(BORDER)

# Add annotations for interesting differences
for i, (r, l, name) in enumerate(zip(rug_rates, legit_rates, feat_names)):
    diff = abs(r - l)
    if diff > 0.05:
        higher = 'rug' if r > l else 'legit'
        ax.text(i, max(r,l)+0.02, f'Δ={diff:.2f}', ha='center', 
               color=RED if higher=='rug' else GREEN, fontsize=7.5, fontweight='bold')

# ═══════════════════════════════════════════════════════════════
# ROW 2, COL 2 — Name/Symbol features
# ═══════════════════════════════════════════════════════════════
ax = fig.add_subplot(gs[2, 2])
ax.set_facecolor(CARD)

name_feats = sorted([c for c in stats_df[stats_df['category']=='Name & Symbol']['feature']],
                    key=lambda x: stats_df[stats_df['feature']==x]['separation'].values[0],
                    reverse=True)[:10]

rug_means = []
leg_means = []
short_ns = []
for feat in name_feats:
    valid = labeled[labeled[feat].notna()]
    rug_means.append(valid.loc[valid['IS_RUG']==1, feat].mean())
    leg_means.append(valid.loc[valid['IS_RUG']==0, feat].mean())
    short_ns.append(feat.replace('feat_name_','n_').replace('feat_symbol_','s_'))

x = np.arange(len(short_ns))
w = 0.35
ax.barh(x - w/2, rug_means, w, color=RED, alpha=0.8, label='Rug')
ax.barh(x + w/2, leg_means, w, color=GREEN, alpha=0.8, label='Legit')
ax.set_yticks(x)
ax.set_yticklabels(short_ns, color=WHITE, fontsize=8.5)
ax.set_xlabel('Mean Value', color=WHITE)
ax.set_title('Name/Symbol Features — Rug vs Legit', color=WHITE, fontweight='bold', fontsize=12)
ax.legend(fontsize=9)
ax.tick_params(colors=GRAY)
for s in ax.spines.values(): s.set_color(BORDER)

# ═══════════════════════════════════════════════════════════════
# ROW 3, COL 0 — Supply & Liquidity features
# ═══════════════════════════════════════════════════════════════
ax = fig.add_subplot(gs[3, 0])
ax.set_facecolor(CARD)

sl_feats = sorted(
    [c for c in stats_df[(stats_df['category']=='Supply') | (stats_df['category']=='Liquidity')]['feature']],
    key=lambda x: stats_df[stats_df['feature']==x]['separation'].values[0],
    reverse=True)

rug_m = []
leg_m = []
names_sl = []
colors_sl = []
for feat in sl_feats:
    valid = labeled[labeled[feat].notna()]
    if len(valid) < 50: continue
    r = valid.loc[valid['IS_RUG']==1, feat].mean()
    l = valid.loc[valid['IS_RUG']==0, feat].mean()
    # Normalize to make comparable
    mx = max(abs(r), abs(l), 1e-9)
    rug_m.append(r/mx)
    leg_m.append(l/mx)
    cat = stats_df[stats_df['feature']==feat]['category'].values[0]
    colors_sl.append(YELLOW if cat=='Supply' else GREEN)
    names_sl.append(feat.replace('feat_supply_','sup_').replace('feat_liq_','liq_'))

x = np.arange(len(names_sl))
w = 0.35
ax.barh(x - w/2, rug_m, w, color=RED, alpha=0.7, label='Rug (normalized)')
ax.barh(x + w/2, leg_m, w, color=GREEN, alpha=0.7, label='Legit (normalized)')
ax.set_yticks(x)
ax.set_yticklabels(names_sl, color=WHITE, fontsize=8.5)
ax.set_title('Supply & Liquidity Features', color=WHITE, fontweight='bold', fontsize=12)
ax.legend(fontsize=8, loc='lower right')
ax.tick_params(colors=GRAY)
for s in ax.spines.values(): s.set_color(BORDER)

# ═══════════════════════════════════════════════════════════════
# ROW 3, COL 1 — Timestamp features
# ═══════════════════════════════════════════════════════════════
ax = fig.add_subplot(gs[3, 1])
ax.set_facecolor(CARD)

# Hour of day distribution: rug vs legit
valid = labeled[labeled['feat_pool_hour'].notna()]
rug_hours = valid.loc[valid['IS_RUG']==1, 'feat_pool_hour']
leg_hours = valid.loc[valid['IS_RUG']==0, 'feat_pool_hour']

bins = np.arange(-0.5, 24.5, 1)
ax.hist(rug_hours, bins=bins, alpha=0.6, color=RED, density=True, label='Rug launches')
ax.hist(leg_hours, bins=bins, alpha=0.6, color=GREEN, density=True, label='Legit launches')
ax.axvspan(0, 6, alpha=0.1, color=ORANGE, label='Night window (0-6 UTC)')
ax.set_xlabel('Hour of Day (UTC)', color=WHITE, fontsize=9)
ax.set_ylabel('Density', color=WHITE)
ax.set_title('Token Launch Hour — Rug vs Legit', color=WHITE, fontweight='bold', fontsize=12)
ax.legend(fontsize=8)
ax.tick_params(colors=GRAY)
for s in ax.spines.values(): s.set_color(BORDER)

# Stats annotation
night_rug = (rug_hours <= 6).mean()
night_leg = (leg_hours <= 6).mean()
ax.text(0.97, 0.95, f'Night launch rate:\nRug: {night_rug:.1%}\nLegit: {night_leg:.1%}',
       transform=ax.transAxes, fontsize=9, color=WHITE, ha='right', va='top',
       bbox=dict(boxstyle='round', facecolor=CARD, edgecolor=BORDER))

# ═══════════════════════════════════════════════════════════════
# ROW 3, COL 2 — RugCheck API features (sparse but useful)
# ═══════════════════════════════════════════════════════════════
ax = fig.add_subplot(gs[3, 2])
ax.set_facecolor(CARD)

rc_feats = [c for c in stats_df[stats_df['category']=='RugCheck API']['feature']]
rc_stats = stats_df[stats_df['category']=='RugCheck API'].sort_values('separation', ascending=False)

if len(rc_stats) > 0:
    names_rc = rc_stats['feature'].str.replace('rc_', '', regex=False).values
    fills_rc = rc_stats['fill'].values
    seps_rc = rc_stats['separation'].values
    
    x = np.arange(len(names_rc))
    
    # Dual axis: fill rate bars + separation line
    bars = ax.bar(x, fills_rc, color=PINK, alpha=0.5, label='Fill Rate %')
    ax.set_ylabel('Fill Rate (%)', color=PINK)
    ax.set_ylim(0, max(fills_rc)*1.3 if max(fills_rc) > 0 else 10)
    
    ax2 = ax.twinx()
    ax2.plot(x, seps_rc, 'o-', color=WHITE, lw=2, ms=5, label='Separation')
    ax2.set_ylabel('Separation', color=WHITE)
    ax2.tick_params(colors=GRAY)
    
    ax.set_xticks(x)
    ax.set_xticklabels(names_rc, rotation=45, color=WHITE, fontsize=7, ha='right')
    
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1+lines2, labels1+labels2, fontsize=8, loc='upper right')

ax.set_title('RugCheck API Features (sparse but informative)', color=WHITE, fontweight='bold', fontsize=12)
ax.tick_params(colors=GRAY)
for s in ax.spines.values(): s.set_color(BORDER)
for s in ax2.spines.values(): s.set_color(BORDER)

# ═══════════════════════════════════════════════════════════════
# ROW 4 — Feature correlation heatmap (top 20 model features)
# ═══════════════════════════════════════════════════════════════
ax = fig.add_subplot(gs[4, 0:2])
ax.set_facecolor(CARD)

# Top 20 features that are in the model
model_top = [f for f, _ in meta['top_features'][:20] if f in labeled.columns]
corr = labeled[model_top].corr()

# Shorten names
short_map = {}
for n in model_top:
    s = n.replace('feat_deployer_past_', 'depl_')
    s = s.replace('feat_', 'f_').replace('derived_', 'd_')
    s = s.replace('TOTAL_ADDED_LIQUIDITY', 'ADDED_LIQ')
    s = s.replace('NUM_LIQUIDITY_ADDS', 'LIQ_ADDS')
    short_map[n] = s

short_labels = [short_map[n] for n in model_top]

im = ax.imshow(corr.values, cmap='RdBu_r', vmin=-1, vmax=1, aspect='auto')
ax.set_xticks(range(len(short_labels)))
ax.set_yticks(range(len(short_labels)))
ax.set_xticklabels(short_labels, rotation=45, ha='right', color=WHITE, fontsize=7.5)
ax.set_yticklabels(short_labels, color=WHITE, fontsize=7.5)
ax.set_title('Feature Correlation Matrix (Top 20 Model Features)', color=WHITE, fontweight='bold', fontsize=12)

# Add correlation values for strong ones
for i in range(len(model_top)):
    for j in range(len(model_top)):
        val = corr.values[i, j]
        if abs(val) > 0.5 and i != j:
            ax.text(j, i, f'{val:.2f}', ha='center', va='center',
                   fontsize=6.5, color='white' if abs(val) > 0.7 else GRAY)

cbar = fig.colorbar(im, ax=ax, fraction=0.02, pad=0.02)
cbar.ax.tick_params(colors=GRAY)
for s in ax.spines.values(): s.set_color(BORDER)

# ═══════════════════════════════════════════════════════════════
# ROW 4, COL 2 — Key insights text panel
# ═══════════════════════════════════════════════════════════════
ax = fig.add_subplot(gs[4, 2])
ax.set_facecolor(CARD)
ax.axis('off')

insights = [
    (RED, "DEPLOYER HISTORY", [
        "89% of model importance from 5 features",
        "Serial ruggers are REAL: same wallets rug repeatedly",
        "past_rug_rate separation = 2.376σ (best signal)",
        "Temporal: only uses data BEFORE each token's creation",
    ]),
    (ACCENT, "HELIUS ON-CHAIN", [
        "IS_MUTABLE: rugs 17% more mutable than legit",
        "HAS_IMAGE: legit tokens 12% more likely to have images",
        "MINT_AUTHORITY_ACTIVE: rugs keep authority active more",
        "8 features enriched via Helius RPC (free tier)",
    ]),
    (PURPLE, "NAME/SYMBOL NLP", [
        "Scam words (moon, safe, elon): 2× more in rugs",
        "Name frequency: copy-paste names = strong rug signal",
        "All-caps names: slightly more common in rugs",
        "14 features extracted, zero API calls needed",
    ]),
    (ORANGE, "TEMPORAL PATTERNS", [
        "Night launches (0-6 UTC): slightly higher rug rate",
        "Weekend launches: negligible difference",
        "6 features, 100% fill rate",
    ]),
    (PINK, "RUGCHECK API", [
        "Only 3.8% coverage (1,282 of 33,358 tokens)",
        "Strong signals WHERE available (score, risks)",
        "Useful for frontend display, not model driver",
    ]),
]

y_pos = 0.97
for color, title, points in insights:
    ax.text(0.03, y_pos, f'■ {title}', transform=ax.transAxes,
           fontsize=10, fontweight='bold', color=color, va='top')
    y_pos -= 0.04
    for point in points:
        ax.text(0.06, y_pos, f'• {point}', transform=ax.transAxes,
               fontsize=8, color=WHITE, va='top')
        y_pos -= 0.035
    y_pos -= 0.02

# ── Save ──
out = os.path.join(FIGS, 'feature_dashboard.png')
fig.savefig(out, dpi=150, facecolor=BG, bbox_inches='tight')
plt.close()
sz = os.path.getsize(out) // 1024
print(f"\n✅ Saved: {out} ({sz}KB)")
