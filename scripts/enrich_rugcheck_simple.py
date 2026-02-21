"""
DeFi Sentinel — Simple RugCheck Enrichment (sync, resumable)
Uses requests instead of aiohttp to avoid async signal issues.
"""
import pandas as pd
import requests
import json
import time
import sys
import os

RC_URL = "https://api.rugcheck.xyz/v1/tokens"
INPUT = "data/enriched/enriched_final.csv"
LABELS = "data/enriched/verified_labels.csv"
CACHE = "data/enriched/_rugcheck_cache.json"
OUTPUT = "data/enriched/rugcheck_enriched.csv"

SAMPLE = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
BATCH_SAVE = 50  # save cache every N tokens


def parse_result(mint, data):
    if not data or "error" in data:
        return None
    risks = data.get("risks") or []
    risk_names = [r.get("name", "") for r in risks]
    risk_levels = [r.get("level", "") for r in risks]
    top_holders = data.get("topHolders") or []
    top10_pct = sum(h.get("pct", 0) for h in top_holders[:10]) if top_holders else None
    top1_pct = top_holders[0].get("pct", 0) if top_holders else None
    markets = data.get("markets") or []
    lp_locked = any(m.get("lp", {}).get("lpLocked", False) for m in markets) if markets else None
    lp_burned = any(m.get("lp", {}).get("lpBurned", False) for m in markets) if markets else None
    lp_lock_pct = max((m.get("lp", {}).get("lpLockedPct", 0) for m in markets), default=0) if markets else None

    return {
        "MINT": mint,
        "rc_score": data.get("score"),
        "rc_score_norm": data.get("score", 0) / 100000 if data.get("score") else None,
        "rc_risks_count": len(risks),
        "rc_top_risk": risk_names[0] if risk_names else None,
        "rc_top_risk_level": risk_levels[0] if risk_levels else None,
        "rc_num_dangers": sum(1 for l in risk_levels if l == "danger"),
        "rc_num_warns": sum(1 for l in risk_levels if l == "warn"),
        "rc_top10_holder_pct": top10_pct,
        "rc_top1_holder_pct": top1_pct,
        "rc_total_holders": data.get("totalHolders"),
        "rc_mint_authority": 1 if data.get("mintAuthority") else 0,
        "rc_freeze_authority": 1 if data.get("freezeAuthority") else 0,
        "rc_mutable_metadata": 1 if data.get("mutableMetadata") else 0,
        "rc_lp_locked": int(lp_locked) if lp_locked is not None else None,
        "rc_lp_burned": int(lp_burned) if lp_burned is not None else None,
        "rc_lp_lock_pct": lp_lock_pct,
        "rc_rugged": 1 if data.get("rugged") else 0,
    }


def main():
    print(f"{'='*60}")
    print(f"  RugCheck Enrichment (sync) — sample={SAMPLE}")
    print(f"{'='*60}")

    df = pd.read_csv(INPUT, low_memory=False)
    labels = pd.read_csv(LABELS, usecols=["MINT", "RUG_LABEL"])
    labels = labels.drop_duplicates("MINT")
    unique = labels[["MINT", "RUG_LABEL"]].copy()
    # Add mints from main df that aren't in labels
    all_mints = df[["MINT"]].drop_duplicates()
    unique = pd.concat([unique, all_mints[~all_mints["MINT"].isin(unique["MINT"])]],
                       ignore_index=True)
    priority = {"VERIFIED_RUG": 0, "LIKELY_RUG": 1, "SUSPICIOUS": 2,
                "LIKELY_LEGIT": 3, "UNCERTAIN": 4}
    unique["_p"] = unique["RUG_LABEL"].map(priority).fillna(5)
    mints = unique.sort_values("_p")["MINT"].tolist()[:SAMPLE]
    print(f"Loaded {len(df):,} rows, sampling {len(mints):,} mints (rugs first)")

    # Load cache
    cache = {}
    if os.path.exists(CACHE):
        with open(CACHE) as f:
            cache = json.load(f)
    print(f"Cache: {len(cache):,} entries")

    todo = [m for m in mints if m not in cache]
    print(f"To fetch: {len(todo):,} mints\n")

    if not todo:
        print("Nothing to fetch!")
    else:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "DeFi-Sentinel-Research/1.0",
            "Accept": "application/json",
        })
        ok = 0
        fail = 0
        rate_limit_count = 0
        for i, mint in enumerate(todo):
            for attempt in range(3):
                try:
                    resp = session.get(f"{RC_URL}/{mint}/report", timeout=15)
                    if resp.status_code == 200:
                        data = resp.json()
                        parsed = parse_result(mint, data)
                        if parsed:
                            cache[mint] = parsed
                            ok += 1
                        else:
                            cache[mint] = {"MINT": mint, "_empty": True}
                        break
                    elif resp.status_code == 429:
                        rate_limit_count += 1
                        wait = 10 * (attempt + 1)
                        if rate_limit_count <= 3:
                            print(f"  429 rate limit at {i}, sleeping {wait}s...")
                        time.sleep(wait)
                        continue
                    else:
                        cache[mint] = {"MINT": mint, "_empty": True}
                        fail += 1
                        break
                except Exception as e:
                    if attempt == 2:
                        cache[mint] = {"MINT": mint, "_empty": True}
                        fail += 1
                    time.sleep(2)

            # Progress
            if (i + 1) % 100 == 0:
                print(f"  [{i+1}/{len(todo)}] ok={ok} fail={fail} rate_limits={rate_limit_count}")

            # Save cache periodically
            if (i + 1) % BATCH_SAVE == 0:
                with open(CACHE, "w") as f:
                    json.dump(cache, f)

            time.sleep(0.15)  # gentle rate limit

        # Final cache save
        with open(CACHE, "w") as f:
            json.dump(cache, f)
        print(f"\n  Fetched: ok={ok}, fail={fail}")

    # Build output CSV
    rows = [v for v in cache.values() if isinstance(v, dict) and not v.get("_empty")]
    if rows:
        rc_df = pd.DataFrame(rows)
        rc_df.to_csv(OUTPUT, index=False)
        print(f"\n  Output: {len(rc_df):,} tokens → {OUTPUT}")
    else:
        print("\n  No RugCheck data found!")

    print(f"\n{'='*60}")
    print(f"  DONE! Cache: {len(cache):,} entries")


if __name__ == "__main__":
    main()
