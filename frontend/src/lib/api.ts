export interface ScanResultData {
  name: string;
  symbol: string;
  mint: string;
  riskScore: number;
  verdict: "SAFE" | "DANGER";
  price: number | null;
  volume24h: number | null;
  marketCap: number | null;
  geckoTerminalUrl: string;
  metrics: {
    mlConfidence: number;
    holders: number;
    liquidity: number;
    poolAge: number;
    mintAuthority: boolean;
    freezeAuthority: boolean;
    rugCheckScore: number;
    topHolderPercent: number;
  };
  riskFactors: {
    level: "critical" | "high" | "medium";
    name: string;
    score: number;
    description: string;
  }[];
  aiAnalysis: string;
  featuresCollected: number;
  totalLatencyMs: number;
  errors: string[];
}

export interface TokenListItem {
  id: string;
  name: string;
  symbol: string;
  mint: string;
  holders: number;
  liquidity: number;
  riskScore: number;
  riskLabel: "SAFE" | "MODERATE" | "DANGER";
  color: string;
  geckoTerminalUrl: string;
  price: number | null;
  volume24h: number | null;
  poolAgeHours: number | null;
}

export async function scanToken(mint: string): Promise<ScanResultData> {
  const res = await fetch(`/api/scan/${mint}`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `Scan failed (${res.status})`);
  }
  return res.json();
}

export async function fetchTokens(): Promise<TokenListItem[]> {
  const res = await fetch("/api/tokens");
  if (!res.ok) {
    throw new Error(`Failed to fetch tokens (${res.status})`);
  }
  return res.json();
}

export async function refreshTokens(): Promise<TokenListItem[]> {
  const res = await fetch("/api/tokens/refresh", { method: "POST" });
  if (!res.ok) {
    throw new Error(`Failed to refresh tokens (${res.status})`);
  }
  return res.json();
}
