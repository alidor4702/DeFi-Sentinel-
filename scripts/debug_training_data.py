"""Check deployer feature distributions in training data."""
import pandas as pd

df = pd.read_csv("data/enriched/enriched_v2.csv")
deployer_cols = [c for c in df.columns if "deployer" in c.lower()]
print("Deployer columns:", deployer_cols)
print(f"\nTotal rows: {len(df)}")
print(f"Labeled rows: {df['IS_RUG'].notna().sum()}")

labeled = df[df["IS_RUG"].notna()]
rugs = labeled[labeled["IS_RUG"] == 1]
legit = labeled[labeled["IS_RUG"] == 0]

print(f"Rugs: {len(rugs)}, Legit: {len(legit)}")

for col in deployer_cols:
    if col not in df.columns:
        continue
    print(f"\n--- {col} ---")
    r_z = (rugs[col] == 0).sum()
    l_z = (legit[col] == 0).sum()
    print(f"  Rugs  mean={rugs[col].mean():.3f}  median={rugs[col].median():.1f}  zeros={r_z}/{len(rugs)} ({r_z/len(rugs)*100:.0f}%)")
    print(f"  Legit mean={legit[col].mean():.3f}  median={legit[col].median():.1f}  zeros={l_z}/{len(legit)} ({l_z/len(legit)*100:.0f}%)")

# KEY QUESTION: deployer_past_labeled = 0 → what does model see?
dpl = "feat_deployer_past_labeled"
dpt = "feat_deployer_past_tokens"
if dpl in df.columns:
    print(f"\n{'='*60}")
    print(f"=== CRITICAL: when {dpl} = 0 ===")
    rug_zero = (rugs[dpl] == 0).sum()
    legit_zero = (legit[dpl] == 0).sum()
    print(f"  Rugs:  {rug_zero}/{len(rugs)} ({rug_zero/len(rugs)*100:.1f}%) have labeled=0")
    print(f"  Legit: {legit_zero}/{len(legit)} ({legit_zero/len(legit)*100:.1f}%) have labeled=0")

    # Among tokens with labeled=0, what % are rugs?
    zero_mask = labeled[dpl] == 0
    zero_rugs = (labeled[zero_mask]["IS_RUG"] == 1).sum()
    zero_total = zero_mask.sum()
    print(f"\n  Tokens with labeled=0: {zero_total}, of which {zero_rugs} are rugs ({zero_rugs/max(zero_total,1)*100:.1f}%)")

    # Among tokens with labeled>0, what % are rugs?
    pos_mask = labeled[dpl] > 0
    pos_rugs = (labeled[pos_mask]["IS_RUG"] == 1).sum()
    pos_total = pos_mask.sum()
    print(f"  Tokens with labeled>0: {pos_total}, of which {pos_rugs} are rugs ({pos_rugs/max(pos_total,1)*100:.1f}%)")

    # Show legit tokens with labeled > 0
    legit_pos = legit[legit[dpl] > 0]
    print(f"\n  Legit tokens with deployer history: {len(legit_pos)}")
    if len(legit_pos) > 0:
        print(f"    {dpl}: mean={legit_pos[dpl].mean():.1f}  median={legit_pos[dpl].median():.0f}")
        print(f"    {dpt}: mean={legit_pos[dpt].mean():.1f}  median={legit_pos[dpt].median():.0f}")
