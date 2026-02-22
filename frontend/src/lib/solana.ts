/* ── Solana on-chain attestation API ────────────────────────── */

export interface AttestationRecord {
  id: string;
  mint: string;
  riskScore: number;
  verdict: string;
  featuresHash: string;
  txSignature: string;
  slot: number;
  network: string;
  attestedAt: string;          // ISO 8601
  explorerUrl: string;
  solscanUrl: string;
  walletAddress: string | null;
}

export interface AttestResponse {
  success: boolean;
  attestation: AttestationRecord;
}

/**
 * Request the backend to create an on-chain risk attestation.
 * If walletAddress/walletSignature are provided, the attestation
 * is cryptographically tied to the user's wallet.
 */
export async function createAttestation(
  mint: string,
  riskScore: number,
  verdict: string,
  featuresCollected: number,
  walletAddress?: string | null,
  walletSignature?: string | null,
  signedMessage?: string | null,
): Promise<AttestResponse> {
  const res = await fetch("/api/attest", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      mint, riskScore, verdict, featuresCollected,
      walletAddress: walletAddress || null,
      walletSignature: walletSignature || null,
      signedMessage: signedMessage || null,
    }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `Attestation failed (${res.status})`);
  }
  return res.json();
}

/**
 * Fetch all past attestation records.
 */
export async function fetchAttestations(): Promise<AttestationRecord[]> {
  const res = await fetch("/api/attestations");
  if (!res.ok) throw new Error(`Failed to fetch attestations (${res.status})`);
  return res.json();
}

/**
 * Fetch attestation(s) for a specific token mint.
 */
export async function fetchAttestationsByMint(mint: string): Promise<AttestationRecord[]> {
  const res = await fetch(`/api/attestations/${mint}`);
  if (!res.ok) throw new Error(`Failed to fetch attestations for ${mint}`);
  return res.json();
}

/**
 * Verify a wallet signature (for wallet-based auth).
 */
export async function verifyWalletSignature(
  publicKey: string,
  signature: string,
  message: string,
): Promise<{ verified: boolean; wallet: string }> {
  const res = await fetch("/api/auth/wallet", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ publicKey, signature, message }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || "Wallet verification failed");
  }
  return res.json();
}

/* ── Payment & Balance APIs ────────────────────────── */

export interface PayerInfo {
  address: string;
  network: string;
  solPrices: Record<string, number>;
}

/** Get the DeFi Sentinel payer wallet address + SOL prices. */
export async function getPayerAddress(): Promise<PayerInfo> {
  const res = await fetch("/api/payer-address");
  if (!res.ok) throw new Error("Failed to fetch payer address");
  return res.json();
}

export interface TokenBalance {
  balance: number;
  decimals: number;
  uiAmount: number;
  hasToken: boolean;
}

/** Check if a wallet holds a specific token (mainnet). */
export async function checkTokenBalance(
  walletAddress: string,
  mint: string,
): Promise<TokenBalance> {
  const res = await fetch(`/api/wallet/${walletAddress}/balance/${mint}`);
  if (!res.ok) return { balance: 0, decimals: 0, uiAmount: 0, hasToken: false };
  return res.json();
}

export interface VerifyPaymentResult {
  success: boolean;
  plan: string;
  creditsAdded: number;
  totalCredits: number;
  txSignature: string;
}

/** Verify a SOL payment and credit scans. */
export async function verifyPayment(
  txSignature: string,
  plan: string,
  walletAddress: string,
): Promise<VerifyPaymentResult> {
  const res = await fetch("/api/verify-solana-payment", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ txSignature, plan, walletAddress }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || "Payment verification failed");
  }
  return res.json();
}

/** Get scan credits for a wallet. */
export async function getCredits(
  walletAddress: string,
): Promise<{ wallet: string; credits: number }> {
  const res = await fetch(`/api/credits/${walletAddress}`);
  if (!res.ok) return { wallet: walletAddress, credits: 0 };
  return res.json();
}

/* ── Wallet Risk Profile ────────────────────────── */

export interface WalletTokenRisk {
  mint: string;
  name: string;
  symbol: string;
  balance: number;
  riskScore: number;
  verdict: string;
  mlConfidence: number;
  liquidity: number;
  price: number | null;
  estimatedValue: number;
  riskFactors: string[];
  error?: string;
}

export interface WalletRiskProfile {
  wallet: string;
  totalTokens: number;
  scannedTokens: number;
  portfolioRiskScore: number;
  riskBreakdown: { danger: number; moderate: number; safe: number };
  totalEstimatedValue: number;
  dangerExposure: number;
  tokens: WalletTokenRisk[];
  summary: string;
}

/** Analyze all tokens in a wallet for rug exposure. */
export async function getWalletRiskProfile(
  walletAddress: string,
): Promise<WalletRiskProfile> {
  const res = await fetch(`/api/wallet/${walletAddress}/risk-profile`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `Risk profile failed (${res.status})`);
  }
  return res.json();
}
