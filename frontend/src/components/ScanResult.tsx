import { useState, useEffect } from "react";
import { Shield, AlertTriangle, Loader2, Database, Brain, Users, Droplets, Clock, Lock, Snowflake, PieChart, TrendingUp, ExternalLink, DollarSign, BarChart3, Star, FileCheck2, CheckCircle2, Link2, Wallet } from "lucide-react";
import { ScanResultData } from "@/lib/api";
import { createAttestation, AttestationRecord, checkTokenBalance, TokenBalance } from "@/lib/solana";
import { useWatchlist } from "@/context/WatchlistContext";
import { useWallet } from "@solana/wallet-adapter-react";
import bs58 from "bs58";

interface ScanResultProps {
  data: ScanResultData | null;
  loading: boolean;
}

const levelColors = {
  critical: "bg-danger/15 text-danger border-danger/30",
  high: "bg-warning/15 text-warning border-warning/30",
  medium: "bg-primary/15 text-primary border-primary/30",
};

function formatUsd(v: number | null | undefined): string {
  if (v == null) return "N/A";
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(1)}K`;
  if (v >= 1) return `$${v.toFixed(2)}`;
  if (v > 0) return `$${v.toFixed(6)}`;
  return "$0";
}

const ScanResult = ({ data, loading }: ScanResultProps) => {
  const { addToWatchlist, removeFromWatchlist, isInWatchlist } = useWatchlist();
  const { publicKey, signMessage } = useWallet();
  const [attesting, setAttesting] = useState(false);
  const [attestation, setAttestation] = useState<AttestationRecord | null>(null);
  const [attestError, setAttestError] = useState("");
  const [tokenBalance, setTokenBalance] = useState<TokenBalance | null>(null);

  // Check if connected wallet holds this token
  useEffect(() => {
    if (data && publicKey) {
      checkTokenBalance(publicKey.toBase58(), data.mint)
        .then(setTokenBalance)
        .catch(() => setTokenBalance(null));
    } else {
      setTokenBalance(null);
    }
  }, [data?.mint, publicKey?.toBase58()]);

  if (loading) {
    return (
      <div className="mt-8 flex flex-col items-center justify-center gap-4 rounded-xl border border-border bg-card p-16">
        <Loader2 className="h-10 w-10 animate-spin text-primary" />
        <p className="text-sm text-muted-foreground">Collecting live data from 5 sources...</p>
        <div className="animate-shimmer h-1 w-48 rounded-full" />
      </div>
    );
  }

  if (!data) return null;

  const isSafe = data.verdict === "SAFE";
  const glowClass = isSafe ? "glow-safe border-safe/40" : "glow-danger border-danger/40";

  // Build metrics grid — swap placeholders when no ML/holder data
  const metricsGrid = [];

  if (data.metrics.mlConfidence > 0) {
    metricsGrid.push({ icon: Brain, label: "ML Confidence", value: `${data.metrics.mlConfidence}%` });
  } else {
    metricsGrid.push({ icon: DollarSign, label: "Price", value: data.price != null ? formatUsd(data.price) : "N/A" });
  }

  if (data.metrics.holders > 0) {
    metricsGrid.push({ icon: Users, label: "Holders", value: data.metrics.holders.toLocaleString() });
  } else {
    metricsGrid.push({ icon: BarChart3, label: "Volume 24h", value: formatUsd(data.volume24h) });
  }

  metricsGrid.push(
    { icon: Droplets, label: "Liquidity", value: formatUsd(data.metrics.liquidity) },
    { icon: Clock, label: "Pool Age", value: `${data.metrics.poolAge} days` },
    { icon: Lock, label: "Mint Authority", value: data.metrics.mintAuthority ? "ENABLED" : "Disabled", danger: data.metrics.mintAuthority },
    { icon: Snowflake, label: "Freeze Authority", value: data.metrics.freezeAuthority ? "ENABLED" : "Disabled", danger: data.metrics.freezeAuthority },
    { icon: Database, label: "RugCheck Score", value: `${data.metrics.rugCheckScore}/100` },
    { icon: PieChart, label: "Top Holder %", value: `${data.metrics.topHolderPercent}%`, danger: data.metrics.topHolderPercent > 50 },
  );

  return (
    <div className={`mt-8 animate-fade-in-up rounded-xl border bg-card p-6 ${glowClass}`}>
      {/* Header */}
      <div className="mb-6 flex items-center gap-5">
        <div
          className={`flex h-20 w-20 items-center justify-center rounded-2xl text-3xl font-black ${
            isSafe ? "bg-safe/15 text-safe" : "bg-danger/15 text-danger"
          }`}
        >
          {data.riskScore}%
        </div>
        <div>
          <div className="flex items-center gap-2">
            {isSafe ? <Shield className="h-5 w-5 text-safe" /> : <AlertTriangle className="h-5 w-5 text-danger" />}
            <span className={`text-xl font-bold ${isSafe ? "text-safe" : "text-danger"}`}>
              {data.verdict}
            </span>
          </div>
          <p className="text-lg font-semibold text-foreground">
            {data.name} ({data.symbol})
          </p>
          <p className="font-mono text-xs text-muted-foreground">
            {data.mint.slice(0, 12)}...{data.mint.slice(-8)}
          </p>
          {/* Token balance indicator */}
          {publicKey && tokenBalance && (
            <div className={`mt-1 flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[10px] font-semibold ${
              tokenBalance.hasToken
                ? "bg-primary/10 border border-primary/30 text-primary"
                : "bg-secondary border border-border text-muted-foreground"
            }`}>
              <Wallet className="h-3 w-3" />
              {tokenBalance.hasToken
                ? `You hold ${tokenBalance.uiAmount.toLocaleString()} ${data.symbol}`
                : "Not in your wallet"}
            </div>
          )}
        </div>
        <button
          onClick={() => {
            if (isInWatchlist(data.mint)) {
              removeFromWatchlist(data.mint);
            } else {
              addToWatchlist({
                mint: data.mint,
                name: data.name,
                symbol: data.symbol,
                riskScore: data.riskScore,
                liquidity: data.metrics.liquidity,
                geckoTerminalUrl: data.geckoTerminalUrl,
                price: data.price,
                poolAgeHours: data.metrics.poolAge * 24,
                addedAt: Date.now(),
              });
            }
          }}
          className={`ml-auto flex h-10 w-10 items-center justify-center rounded-lg border transition-colors ${
            isInWatchlist(data.mint)
              ? "border-primary/30 bg-primary/15 text-primary hover:bg-primary/10"
              : "border-border bg-secondary text-muted-foreground hover:text-primary"
          }`}
        >
          <Star className={`h-5 w-5 ${isInWatchlist(data.mint) ? "fill-current" : ""}`} />
        </button>
      </div>

      {/* Risk meter */}
      <div className="mb-8">
        <div className="relative h-3 w-full overflow-hidden rounded-full">
          <div className="absolute inset-0 bg-gradient-to-r from-safe via-warning to-danger" />
          <div
            className="absolute top-1/2 h-5 w-5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-foreground bg-foreground shadow-lg transition-all duration-700"
            style={{ left: `${data.riskScore}%` }}
          />
        </div>
        <div className="mt-1.5 flex justify-between text-[10px] text-muted-foreground">
          <span>Safe</span>
          <span>Moderate</span>
          <span>Dangerous</span>
        </div>
      </div>

      {/* Metrics grid */}
      <div className="mb-8 grid grid-cols-2 gap-3 md:grid-cols-4">
        {metricsGrid.map(({ icon: Icon, label, value, danger }, i) => (
          <div key={i} className="rounded-lg border border-border bg-secondary/50 p-3">
            <div className="flex items-center gap-1.5">
              <Icon className="h-3.5 w-3.5 text-muted-foreground" />
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</span>
            </div>
            <p className={`mt-1 text-sm font-bold ${danger ? "text-danger" : "text-foreground"}`}>{value}</p>
          </div>
        ))}
      </div>

      {/* Risk factors */}
      {data.riskFactors.length > 0 && (
        <div className="mb-8">
          <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
            <AlertTriangle className="h-4 w-4 text-danger" />
            Risk Factors
          </h3>
          <div className="space-y-2">
            {data.riskFactors.map((factor, i) => (
              <div key={i} className={`rounded-lg border p-3 ${levelColors[factor.level]}`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="rounded-md bg-current/10 px-1.5 py-0.5 text-[10px] font-bold uppercase">
                      {factor.level}
                    </span>
                    <span className="text-sm font-semibold">{factor.name}</span>
                  </div>
                  <span className="text-xs font-bold">+{factor.score} pts</span>
                </div>
                <p className="mt-1 text-xs opacity-80">{factor.description}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* AI Analysis */}
      <div className="mb-6 rounded-lg border border-primary/20 bg-primary/5 p-4">
        <div className="mb-2 flex items-center gap-2">
          <Brain className="h-4 w-4 text-primary" />
          <h3 className="text-sm font-semibold text-primary">AI Analysis</h3>
        </div>
        <p className="text-sm leading-relaxed text-foreground/80">{data.aiAnalysis}</p>
      </div>

      {/* Data sources + GeckoTerminal link */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[10px] text-muted-foreground">Data sources:</span>
        {["RugCheck", "GeckoTerminal", "Helius", "Jupiter"].map((s) => (
          <span key={s} className="rounded-full border border-border bg-secondary px-2 py-0.5 text-[10px] text-muted-foreground">
            {s}
          </span>
        ))}
      </div>

      <div className="mt-4 flex items-center justify-between">
        <a
          href={data.geckoTerminalUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-secondary px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-secondary/80"
        >
          <ExternalLink className="h-3.5 w-3.5" />
          View on GeckoTerminal
        </a>
        <span className="text-[10px] text-muted-foreground">
          {data.featuresCollected} features collected in {(data.totalLatencyMs / 1000).toFixed(1)}s
          {data.errors.length > 0 && ` · ${data.errors.length} error${data.errors.length > 1 ? "s" : ""}`}
        </span>
      </div>

      {/* ── On-chain Attestation Section ───────────────── */}
      <div className="mt-6 rounded-lg border border-primary/20 bg-card p-4">
        <div className="mb-3 flex items-center gap-2">
          <FileCheck2 className="h-4 w-4 text-primary" />
          <h3 className="text-sm font-semibold text-foreground">On-chain Risk Attestation</h3>
          <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-primary">
            Solana
          </span>
        </div>

        {attestation ? (
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-safe">
              <CheckCircle2 className="h-4 w-4" />
              <span className="text-sm font-semibold">Attestation recorded on Solana {attestation.network}</span>
            </div>
            {attestation.walletAddress && (
              <div className="flex items-center gap-1.5 rounded-full bg-primary/10 border border-primary/30 px-2.5 py-1 w-fit">
                <Wallet className="h-3 w-3 text-primary" />
                <span className="text-[10px] font-semibold text-primary">
                  Signed by {attestation.walletAddress.slice(0, 4)}...{attestation.walletAddress.slice(-4)}
                </span>
              </div>
            )}
            <div className="rounded-lg bg-secondary/50 p-3 space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Transaction</span>
                <span className="font-mono text-xs text-foreground">
                  {attestation.txSignature.slice(0, 12)}...{attestation.txSignature.slice(-8)}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Hash</span>
                <span className="font-mono text-xs text-foreground">
                  {attestation.featuresHash.slice(0, 16)}...
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Time</span>
                <span className="text-xs text-foreground">
                  {new Date(attestation.attestedAt).toLocaleString()}
                </span>
              </div>
            </div>
            <div className="flex gap-2 mt-2">
              <a
                href={attestation.explorerUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 rounded-lg border border-primary/30 bg-primary/10 px-3 py-1.5 text-xs font-medium text-primary transition-colors hover:bg-primary/20"
              >
                <Link2 className="h-3 w-3" />
                Solana Explorer
              </a>
              <a
                href={attestation.solscanUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-secondary px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-secondary/80"
              >
                <ExternalLink className="h-3 w-3" />
                Solscan
              </a>
            </div>
          </div>
        ) : (
          <div>
            <p className="text-xs text-muted-foreground mb-3">
              Record this risk assessment permanently on the Solana blockchain. Creates an immutable,
              verifiable attestation using the Memo program.
            </p>
            {attestError && (
              <p className="mb-2 rounded-lg bg-danger/10 px-3 py-2 text-xs text-danger">{attestError}</p>
            )}
            <button
              onClick={async () => {
                setAttesting(true);
                setAttestError("");
                try {
                  let walletAddr: string | null = null;
                  let walletSig: string | null = null;
                  let signedMsg: string | null = null;

                  // If wallet connected, ask user to sign the attestation
                  if (publicKey && signMessage) {
                    const ts = new Date().toISOString();
                    const msg = `DeFi Sentinel Attestation\nMint: ${data.mint}\nRisk: ${data.riskScore}\nVerdict: ${data.verdict}\nTime: ${ts}`;
                    const msgBytes = new TextEncoder().encode(msg);
                    const sig = await signMessage(msgBytes);
                    walletAddr = publicKey.toBase58();
                    walletSig = bs58.encode(sig);
                    signedMsg = msg;
                  }

                  const res = await createAttestation(
                    data.mint,
                    data.riskScore,
                    data.verdict,
                    data.featuresCollected,
                    walletAddr,
                    walletSig,
                    signedMsg,
                  );
                  setAttestation(res.attestation);
                } catch (e: any) {
                  setAttestError(e.message || "Attestation failed");
                } finally {
                  setAttesting(false);
                }
              }}
              disabled={attesting}
              className="inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold text-white transition-all hover:opacity-90 disabled:opacity-50"
              style={{ background: "linear-gradient(135deg, #9945FF, #14F195)" }}
            >
              {attesting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {publicKey ? "Sign & Attest..." : "Writing to Solana..."}
                </>
              ) : (
                <>
                  <FileCheck2 className="h-4 w-4" />
                  {publicKey ? "Sign & Attest on Solana" : "Attest on Solana"}
                </>
              )}
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default ScanResult;
