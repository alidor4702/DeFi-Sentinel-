# DeFi Sentinel — 2-Minute Demo Script

> **Format:** Screen recording walkthrough. Keep it fast-paced and confident.
> **Tone:** Builder showing a working product, not a pitch deck.

---

## 🎬 INTRO (0:00 – 0:15)

**Show:** Connect page (not logged in)

> "Every day, hundreds of new tokens launch on Solana. Most of them are scams — rug pulls that drain liquidity the moment people buy in. There's no easy way to tell which ones are safe before it's too late.
>
> DeFi Sentinel fixes that. It's a real-time AI-powered rug-pull detection platform for Solana."

**Action:** Click "Select Wallet" → Phantom popup appears → approve connection.

---

## 🔐 WALLET CONNECT (0:15 – 0:25)

**Show:** Phantom approval popup → connected state → Pricing page loads

> "We support wallet-based auth via Phantom and Solflare. Once connected, you're in — no email required. You can also sign in with email if you prefer."

**Action:** Briefly show the Pricing section (Pro $9.99/mo, Enterprise $99.99/mo, scan packs with SOL prices). Don't click anything — just scroll past it.

> "We have Stripe subscriptions and direct SOL payments for scan credit packs."

---

## 📊 DASHBOARD — LIVE FEED (0:25 – 0:50)

**Action:** Click "Dashboard" in the nav bar.

**Show:** The dashboard with stat cards + two tables side by side

> "The dashboard monitors Solana in real-time. On the left, the **Live Feed** shows the newest token launches scored in real-time — we're pulling data from six different APIs: Helius, RugCheck, GoPlus, GeckoTerminal, Jupiter, and on-chain data."

**Action:** Point out the stat cards (Pools Monitored, Rugs Detected, Safe Tokens, Data Sources).

> "Each token gets a risk score from our XGBoost ML model that was trained on over 116,000 liquidity pool records. Green means safe, red means danger."

**Action:** Move to the right table — the Risk Scanner.

> "The **Risk Scanner** lets you filter by risk threshold. I can drag this slider down to only show tokens below, say, 40% risk — so only the safer ones. You can also sort by liquidity to find high-value targets."

**Action:** Drag the slider from 80 down to ~40, show results filtering.

---

## 🔍 TOKEN SCAN (0:50 – 1:15)

**Action:** Click on any token from the dashboard (or click "Scan Token" in nav).

**Show:** The ScanResult card loading, then the full result.

> "Let's deep-scan this token. DeFi Sentinel collects 77 features in real-time — liquidity, mint authority, freeze authority, holder concentration, pool age, RugCheck score, and more."

**Action:** Point to the risk score box, the verdict (SAFE/DANGER), the risk meter bar.

> "We get a clear verdict: SAFE or DANGER, with an exact risk percentage. Below that, every risk factor is explained — what's wrong, how severe it is, and how many points it contributes."

**Action:** Scroll down to show the AI Analysis section.

> "The AI analysis gives a plain-English explanation of why this token is rated the way it is."

**Action:** Scroll to the data sources badges (RugCheck, GeckoTerminal, Helius, Jupiter).

> "You can see exactly which data sources contributed — full transparency."

---

## ⛓️ ON-CHAIN ATTESTATION (1:15 – 1:30)

**Action:** Scroll to the "On-chain Risk Attestation" section at the bottom of the scan result.

> "Here's what makes us different. You can permanently record this risk assessment on the Solana blockchain. Click 'Sign & Attest' — Phantom asks you to sign the attestation message..."

**Action:** Click "Sign & Attest on Solana" → Phantom sign popup → approve.

**Show:** The attestation confirmation with tx signature, features hash, Solana Explorer link, Solscan link.

> "...and it's written to Solana devnet via the Memo program. Immutable, verifiable, timestamped. You can verify it on Solana Explorer right here."

---

## 👛 WALLET RISK PROFILE (1:30 – 1:45)

**Action:** Click "Wallet Risk" in the nav bar.

**Show:** The portfolio risk gauge, holdings count, risk breakdown, danger exposure, individual token cards.

> "The Wallet Risk Profile scans every token in your connected wallet. It runs the ML model on each one and gives you a portfolio-level risk score. You can see exactly how much dollar value is sitting in dangerous tokens."

**Action:** Point to the risk gauge (circular), the breakdown (Danger/Moderate/Safe), and the AI summary.

> "Each holding shows its individual risk score, and you can click 'Deep Scan' to get the full breakdown."

---

## 📜 ATTESTATIONS LOG (1:45 – 1:55)

**Action:** Click "Attestations" in the nav bar.

**Show:** The attestation log table with tx signatures, verdicts, timestamps, explorer links.

> "Every attestation we've ever published is logged here — searchable, with direct links to Solana Explorer and Solscan. This creates a public, on-chain audit trail of risk assessments that anyone can verify."

---

## 🎯 CLOSING (1:55 – 2:00)

**Action:** Go back to Dashboard, show the live feed updating.

> "DeFi Sentinel: real-time AI rug detection, 77-feature ML scoring, on-chain attestations, and wallet risk profiling — all built on Solana. Thanks for watching."

---

## 🔑 Key Talking Points to Hit

If judges ask questions, emphasize these:

| Point | Detail |
|-------|--------|
| **ML Model** | XGBoost v4, AUC 0.999, trained on SolRPDS dataset (CODASPY 2025), 77 features, temporal train/test split |
| **Data Pipeline** | 6 real-time APIs enriching 12 raw columns → 113 features (9.4× enrichment) |
| **On-chain** | Solana Memo program attestations — immutable, verifiable risk records |
| **Wallet Integration** | Phantom/Solflare via @solana/wallet-adapter, SOL payments, wallet risk scanning |
| **Monetization** | Stripe subscriptions ($9.99/$99.99) + SOL scan packs — dual payment rails |
| **Dataset** | 116,308 pool records, 33,358 unique mints, temporal split for leak-free evaluation |
