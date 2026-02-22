import { useState, useEffect } from "react";
import {
  Shield,
  AlertTriangle,
  CheckCircle2,
  Loader2,
  Wallet,
  ExternalLink,
  TrendingDown,
  TrendingUp,
  Ban,
  RefreshCw,
} from "lucide-react";
import { useWallet } from "@solana/wallet-adapter-react";
import { WalletMultiButton } from "@solana/wallet-adapter-react-ui";
import { getWalletRiskProfile, WalletRiskProfile, WalletTokenRisk } from "@/lib/solana";
import { Link } from "react-router-dom";

const verdictColor = (verdict: string) => {
  switch (verdict) {
    case "DANGER":
      return "text-danger";
    case "MODERATE":
      return "text-warning";
    case "SAFE":
      return "text-safe";
    default:
      return "text-muted-foreground";
  }
};

const verdictBg = (verdict: string) => {
  switch (verdict) {
    case "DANGER":
      return "bg-danger/10 border-danger/30";
    case "MODERATE":
      return "bg-warning/10 border-warning/30";
    case "SAFE":
      return "bg-safe/10 border-safe/30";
    default:
      return "bg-muted border-border";
  }
};

const riskGradient = (score: number) => {
  if (score >= 70) return "from-danger to-danger/60";
  if (score >= 40) return "from-warning to-warning/60";
  return "from-safe to-safe/60";
};

function RiskGauge({ score }: { score: number }) {
  const color = score >= 70 ? "#ef4444" : score >= 40 ? "#f59e0b" : "#00e5a0";
  const pct = Math.min(score, 100);
  return (
    <div className="flex flex-col items-center">
      <div className="relative h-32 w-32">
        <svg viewBox="0 0 120 120" className="h-full w-full -rotate-90">
          <circle cx="60" cy="60" r="50" fill="none" stroke="currentColor" strokeWidth="8" className="text-border" />
          <circle
            cx="60"
            cy="60"
            r="50"
            fill="none"
            stroke={color}
            strokeWidth="8"
            strokeDasharray={`${(pct / 100) * 314} 314`}
            strokeLinecap="round"
            className="transition-all duration-1000"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-3xl font-black" style={{ color }}>
            {score}
          </span>
          <span className="text-[10px] font-semibold text-muted-foreground">/ 100</span>
        </div>
      </div>
      <span className="mt-1 text-xs font-semibold text-muted-foreground">PORTFOLIO RISK</span>
    </div>
  );
}

function TokenRow({ token }: { token: WalletTokenRisk }) {
  const isError = token.riskScore < 0;
  return (
    <div className={`flex items-center gap-4 rounded-lg border p-4 transition-all hover:bg-secondary/30 ${verdictBg(token.verdict)}`}>
      {/* Risk score pill */}
      <div className={`flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-full bg-gradient-to-br ${riskGradient(token.riskScore)}`}>
        {isError ? (
          <Ban className="h-5 w-5 text-white" />
        ) : (
          <span className="text-sm font-black text-white">{token.riskScore}</span>
        )}
      </div>

      {/* Token info */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate font-semibold text-foreground">{token.name}</span>
          <span className="text-xs text-muted-foreground">{token.symbol}</span>
          <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${verdictColor(token.verdict)}`}>
            {token.verdict}
          </span>
        </div>
        <div className="mt-1 flex flex-wrap gap-3 text-xs text-muted-foreground">
          <span>Balance: {token.balance.toLocaleString(undefined, { maximumFractionDigits: 4 })}</span>
          {token.price != null && <span>Price: ${token.price.toFixed(6)}</span>}
          {token.estimatedValue > 0 && <span>Value: ${token.estimatedValue.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>}
          {token.liquidity > 0 && <span>Liq: ${token.liquidity.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>}
        </div>
        {token.riskFactors.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {token.riskFactors.slice(0, 4).map((rf, i) => (
              <span key={i} className="rounded-full bg-danger/10 px-2 py-0.5 text-[10px] font-medium text-danger">
                {rf}
              </span>
            ))}
          </div>
        )}
        {token.error && (
          <p className="mt-1 text-[10px] text-muted-foreground">Scan failed: {token.error}</p>
        )}
      </div>

      {/* Actions */}
      <div className="flex flex-shrink-0 items-center gap-2">
        <Link
          to={`/scan/${token.mint}`}
          className="rounded-lg bg-primary/10 px-3 py-1.5 text-xs font-semibold text-primary transition-colors hover:bg-primary/20"
        >
          Deep Scan
        </Link>
        <a
          href={`https://www.geckoterminal.com/solana/tokens/${token.mint}`}
          target="_blank"
          rel="noreferrer"
          className="rounded-lg bg-secondary p-1.5 text-muted-foreground transition-colors hover:text-foreground"
        >
          <ExternalLink className="h-3.5 w-3.5" />
        </a>
      </div>
    </div>
  );
}

const WalletRisk = () => {
  const { publicKey } = useWallet();
  const [profile, setProfile] = useState<WalletRiskProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const analyze = async () => {
    if (!publicKey) return;
    setLoading(true);
    setError("");
    setProfile(null);
    try {
      const result = await getWalletRiskProfile(publicKey.toBase58());
      setProfile(result);
    } catch (err: any) {
      setError(err.message || "Failed to analyze wallet");
    } finally {
      setLoading(false);
    }
  };

  // Auto-analyze when wallet connects
  useEffect(() => {
    if (publicKey) analyze();
  }, [publicKey?.toBase58()]);

  if (!publicKey) {
    return (
      <div className="container max-w-3xl py-20 text-center">
        <Shield className="mx-auto mb-4 h-16 w-16 text-primary/40" />
        <h1 className="text-2xl font-bold text-foreground">Wallet Risk Profile</h1>
        <p className="mt-2 text-muted-foreground">
          Connect your Phantom wallet to analyze all your token holdings for rug-pull exposure.
        </p>
        <div className="mt-8 flex justify-center">
          <WalletMultiButton
            style={{
              height: "44px",
              borderRadius: "12px",
              fontSize: "14px",
              fontWeight: 600,
              padding: "0 24px",
              background: "linear-gradient(135deg, #9945FF, #14F195)",
            }}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="container max-w-4xl py-8">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Wallet Risk Profile</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            AI-powered rug exposure analysis of your Solana holdings
          </p>
        </div>
        <button
          onClick={analyze}
          disabled={loading}
          className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white transition-all hover:opacity-90 disabled:opacity-50"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          {loading ? "Scanning..." : "Re-analyze"}
        </button>
      </div>

      {error && (
        <div className="mb-6 rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
          {error}
        </div>
      )}

      {loading && !profile && (
        <div className="flex flex-col items-center py-20">
          <Loader2 className="mb-4 h-12 w-12 animate-spin text-primary" />
          <p className="text-lg font-semibold text-foreground">Analyzing your wallet...</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Scanning token holdings and running ML risk models on each
          </p>
        </div>
      )}

      {profile && (
        <>
          {/* Summary Cards */}
          <div className="mb-8 grid gap-4 md:grid-cols-4">
            <div className="flex flex-col items-center rounded-xl border border-border bg-card p-5">
              <RiskGauge score={profile.portfolioRiskScore} />
            </div>

            <div className="rounded-xl border border-border bg-card p-5">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Wallet className="h-4 w-4" />
                Holdings
              </div>
              <p className="mt-2 text-3xl font-black text-foreground">{profile.totalTokens}</p>
              <p className="text-xs text-muted-foreground">{profile.scannedTokens} scanned</p>
              {(profile.totalEstimatedValue ?? 0) > 0 && (
                <p className="mt-2 text-sm font-semibold text-primary">
                  ~${(profile.totalEstimatedValue ?? 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}
                </p>
              )}
            </div>

            <div className="rounded-xl border border-border bg-card p-5">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <AlertTriangle className="h-4 w-4" />
                Risk Breakdown
              </div>
              <div className="mt-3 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-1 text-xs text-danger">
                    <TrendingDown className="h-3 w-3" /> Danger
                  </span>
                  <span className="text-sm font-bold text-danger">{profile.riskBreakdown.danger}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-1 text-xs text-warning">
                    <AlertTriangle className="h-3 w-3" /> Moderate
                  </span>
                  <span className="text-sm font-bold text-warning">{profile.riskBreakdown.moderate}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-1 text-xs text-safe">
                    <TrendingUp className="h-3 w-3" /> Safe
                  </span>
                  <span className="text-sm font-bold text-safe">{profile.riskBreakdown.safe}</span>
                </div>
              </div>
            </div>

            <div className="rounded-xl border border-border bg-card p-5">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Shield className="h-4 w-4" />
                Danger Exposure
              </div>
              <p className="mt-2 text-3xl font-black text-danger">
                ${(profile.dangerExposure ?? 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}
              </p>
              <p className="text-xs text-muted-foreground">at risk</p>
            </div>
          </div>

          {/* AI Summary */}
          <div className="mb-6 rounded-xl border border-primary/30 bg-primary/5 px-5 py-4">
            <div className="flex items-start gap-3">
              <CheckCircle2 className="mt-0.5 h-5 w-5 flex-shrink-0 text-primary" />
              <div>
                <p className="text-sm font-semibold text-foreground">AI Analysis</p>
                <p className="mt-1 text-sm text-muted-foreground">{profile.summary}</p>
              </div>
            </div>
          </div>

          {/* Token List */}
          <h2 className="mb-4 text-lg font-bold text-foreground">
            Token Holdings ({profile.tokens.length})
          </h2>
          <div className="space-y-3">
            {profile.tokens.map((token) => (
              <TokenRow key={token.mint} token={token} />
            ))}
          </div>

          {profile.totalTokens > profile.scannedTokens && (
            <p className="mt-4 text-center text-xs text-muted-foreground">
              Showing top {profile.scannedTokens} of {profile.totalTokens} tokens (limited for performance)
            </p>
          )}
        </>
      )}
    </div>
  );
};

export default WalletRisk;
