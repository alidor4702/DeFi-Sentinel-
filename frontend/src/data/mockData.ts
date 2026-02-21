export interface Token {
  id: string;
  name: string;
  symbol: string;
  mint: string;
  holders: number;
  liquidity: number;
  riskScore: number;
  color: string;
  timeAgo: string;
}

export const MOCK_TOKENS: Token[] = [
  { id: "1", name: "Bonk", symbol: "BONK", mint: "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", holders: 842000, liquidity: 24500000, riskScore: 2, color: "#f59e0b", timeAgo: "2s ago" },
  { id: "2", name: "USD Coin", symbol: "USDC", mint: "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", holders: 2100000, liquidity: 890000000, riskScore: 1, color: "#2775ca", timeAgo: "5s ago" },
  { id: "3", name: "MoonShot", symbol: "MOON", mint: "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU", holders: 34, liquidity: 62, riskScore: 92, color: "#ef4444", timeAgo: "8s ago" },
  { id: "4", name: "Jupiter", symbol: "JUP", mint: "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN", holders: 456000, liquidity: 78000000, riskScore: 3, color: "#6366f1", timeAgo: "12s ago" },
  { id: "5", name: "RugFast", symbol: "RUGF", mint: "RUGfa5t9xk2mBhYZPaKmN3FqJGS7cPVn3VQy8zRJK1", holders: 12, liquidity: 8, riskScore: 98, color: "#dc2626", timeAgo: "15s ago" },
  { id: "6", name: "Raydium", symbol: "RAY", mint: "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R", holders: 234000, liquidity: 45000000, riskScore: 4, color: "#c084fc", timeAgo: "18s ago" },
  { id: "7", name: "SCAM100X", symbol: "SCAM", mint: "SCAMxyz123abc456def789ghi012jkl345mno678pqr", holders: 8, liquidity: 3, riskScore: 99, color: "#ef4444", timeAgo: "22s ago" },
  { id: "8", name: "Solana", symbol: "SOL", mint: "So11111111111111111111111111111111111111112", holders: 5200000, liquidity: 3200000000, riskScore: 1, color: "#9945ff", timeAgo: "25s ago" },
  { id: "9", name: "ElonDoge", symbol: "EDOGE", mint: "ELONd0g3xyzABC123DEF456GHI789JKL012MNO345P", holders: 22, liquidity: 45, riskScore: 95, color: "#f97316", timeAgo: "30s ago" },
  { id: "10", name: "Marinade", symbol: "MNDE", mint: "MNDEFzGvMt87ueuHvVU9VcTqsAP5b3fTGPsHuuPA5ey", holders: 89000, liquidity: 12000000, riskScore: 5, color: "#22d3ee", timeAgo: "35s ago" },
  { id: "11", name: "SafeMoon2", symbol: "SM2", mint: "SM2fake123456789abcdefghijklmnopqrstuvwxy", holders: 15, liquidity: 120, riskScore: 88, color: "#f43f5e", timeAgo: "40s ago" },
  { id: "12", name: "Orca", symbol: "ORCA", mint: "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE", holders: 167000, liquidity: 34000000, riskScore: 3, color: "#fcd34d", timeAgo: "45s ago" },
];

export const SAFE_TOKEN_RESULT = {
  name: "USD Coin",
  symbol: "USDC",
  mint: "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
  riskScore: 1,
  verdict: "SAFE" as const,
  metrics: {
    mlConfidence: 99.8,
    holders: 2100000,
    liquidity: 890000000,
    poolAge: 1247,
    mintAuthority: false,
    freezeAuthority: false,
    rugCheckScore: 98,
    topHolderPercent: 4.2,
  },
  riskFactors: [],
  aiAnalysis: "This token (USDC) is a well-established stablecoin issued by Circle and Coinbase. It has extremely high liquidity ($890M), over 2.1 million holders, and has been active for over 3 years. Mint and freeze authorities are properly disabled. Our ML model assigns a 99.8% confidence that this is a legitimate, safe token. No risk factors were detected.",
};

export const DANGER_TOKEN_RESULT = {
  name: "MoonShot",
  symbol: "MOON",
  mint: "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
  riskScore: 89,
  verdict: "DANGER" as const,
  metrics: {
    mlConfidence: 94.1,
    holders: 34,
    liquidity: 62,
    poolAge: 0.3,
    mintAuthority: true,
    freezeAuthority: true,
    rugCheckScore: 12,
    topHolderPercent: 87.4,
  },
  riskFactors: [
    { level: "critical" as const, name: "Mint Authority Enabled", score: 35, description: "Creator can print unlimited tokens at any time, diluting existing holders to zero." },
    { level: "critical" as const, name: "Extreme Holder Concentration", score: 25, description: "Top wallet holds 87.4% of supply. A single sell would crash the price instantly." },
    { level: "high" as const, name: "Critical Low Liquidity", score: 20, description: "Only $62 in pool. Any trade will cause massive slippage." },
    { level: "high" as const, name: "Pool Age < 1 Day", score: 15, description: "Pool is only 7 hours old. Matches the timing pattern of 94% of detected rug pulls." },
    { level: "medium" as const, name: "Freeze Authority Enabled", score: 10, description: "Creator can freeze your tokens, preventing any transfers or sales." },
  ],
  aiAnalysis: "⚠️ EXTREME CAUTION: This token exhibits every major red flag in our detection model. The mint authority is still enabled, meaning the creator can inflate supply infinitely. One wallet controls 87.4% of all tokens — a classic rug pull setup. Liquidity is critically low at $62, and the pool was created just 7 hours ago. Our ML model, trained on 116,000+ rug pull events, assigns an 89% probability this is a scam. We strongly recommend NOT trading this token.",
};

export const COMMUNITY_SCANS = [
  { name: "BONK", safe: true, riskScore: 2, time: "1m ago" },
  { name: "RUGFAST", safe: false, riskScore: 98, time: "3m ago" },
  { name: "JUP", safe: true, riskScore: 3, time: "5m ago" },
  { name: "SCAM100X", safe: false, riskScore: 99, time: "7m ago" },
  { name: "SOL", safe: true, riskScore: 1, time: "8m ago" },
  { name: "EDOGE", safe: false, riskScore: 95, time: "12m ago" },
  { name: "RAY", safe: true, riskScore: 4, time: "15m ago" },
  { name: "SM2", safe: false, riskScore: 88, time: "18m ago" },
  { name: "ORCA", safe: true, riskScore: 3, time: "22m ago" },
  { name: "MNDE", safe: true, riskScore: 5, time: "25m ago" },
];
