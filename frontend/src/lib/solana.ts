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
}

export interface AttestResponse {
  success: boolean;
  attestation: AttestationRecord;
}

/**
 * Request the backend to create an on-chain risk attestation.
 * The backend sends a Solana transaction with a memo containing
 * the risk score hash, then stores the record.
 */
export async function createAttestation(
  mint: string,
  riskScore: number,
  verdict: string,
  featuresCollected: number,
): Promise<AttestResponse> {
  const res = await fetch("/api/attest", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mint, riskScore, verdict, featuresCollected }),
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
