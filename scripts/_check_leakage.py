"""Check if derived_has_price / TOKEN_PRICE_USD are leaking label info."""
import pandas as pd

df = pd.read_csv("data/enriched/enriched_clean.csv", low_memory=False)
labels = pd.read_csv("data/enriched/verified_labels.csv")
df = df.merge(labels[["MINT","LIQUIDITY_POOL_ADDRESS","RUG_LABEL"]],
              on=["MINT","LIQUIDITY_POOL_ADDRESS"], how="left")
rug = df["RUG_LABEL"].isin(["VERIFIED_RUG","LIKELY_RUG"])
legit = df["RUG_LABEL"] == "LIKELY_LEGIT"
lab = df[rug | legit].copy()
lab["IS_RUG"] = rug[lab.index].astype(int)

print("=== derived_has_price vs IS_RUG ===")
ct = pd.crosstab(lab["IS_RUG"], lab["derived_has_price"], margins=True)
print(ct)
rp = lab[lab["IS_RUG"]==1]["derived_has_price"].mean()
lp = lab[lab["IS_RUG"]==0]["derived_has_price"].mean()
print(f"\nRug tokens with price:   {rp*100:.2f}%")
print(f"Legit tokens with price: {lp*100:.2f}%")

print("\n=== TOKEN_PRICE_USD ===")
r_price = lab[lab["IS_RUG"]==1]["TOKEN_PRICE_USD"].notna().mean()
l_price = lab[lab["IS_RUG"]==0]["TOKEN_PRICE_USD"].notna().mean()
print(f"Rug tokens with USD price:   {r_price*100:.2f}%")
print(f"Legit tokens with USD price: {l_price*100:.2f}%")

print("\n=== Checking verified_labels construction ===")
vl = pd.read_csv("data/enriched/verified_labels.csv")
print("Columns:", list(vl.columns))
# Check: were the labels built using SIG_NO_PRICE?
if "SIG_NO_PRICE" in vl.columns:
    print("\nSIG_NO_PRICE is in verified_labels!")
    # Among LIKELY_RUG, how many have SIG_NO_PRICE=1?
    lr = vl[vl["RUG_LABEL"]=="LIKELY_RUG"]
    ll = vl[vl["RUG_LABEL"]=="LIKELY_LEGIT"]
    print(f"LIKELY_RUG   SIG_NO_PRICE mean: {lr['SIG_NO_PRICE'].mean():.4f}")
    print(f"LIKELY_LEGIT SIG_NO_PRICE mean: {ll['SIG_NO_PRICE'].mean():.4f}")

print("\n=== Why is the model perfect? ===")
print("If 99.5% of rugs have no price and 85% of legit have price,")
print("then derived_has_price alone gives near-perfect separation.")
print("This is NOT leakage — rug tokens genuinely lose their price")
print("because the pool is drained. The question is: can we detect")
print("BEFORE the drain (at token creation time, price exists)?")
print("\nFor LIVE inference: every new token starts WITH a price,")
print("so derived_has_price=1 for ALL tokens at creation time.")
print("This feature is useless for prediction — it only works after the fact.")
